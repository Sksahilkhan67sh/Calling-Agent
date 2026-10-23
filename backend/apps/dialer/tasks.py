import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.calls.models import CallAttempt
from apps.calls.services import fail_attempt
from apps.campaigns.models import Campaign
from apps.contacts.models import Contact
from apps.suppression.services import is_suppressed
from apps.voice_runtime.client import DialOutcomeUnknown, DograhClient, DograhError, StartCallRequest

log = logging.getLogger(__name__)
A, C = CallAttempt.State, Contact.Status
BATCH, LEASE, DIAL_LOCK = 100, timedelta(seconds=60), 7_040_001


def _window_wait(now, policy):
    t = now.timetz().replace(tzinfo=None)  # [verify] docs give no window timezone; UTC (TIME_ZONE) is the fallback
    if policy.window_start <= t < policy.window_end:
        return None
    day = now.date() if t < policy.window_start else now.date() + timedelta(days=1)
    return datetime.combine(day, policy.window_start, tzinfo=now.tzinfo)


@shared_task(queue="dial")
def dispatch_due():
    now = timezone.now()
    with transaction.atomic():
        fresh = list(Contact.objects.select_for_update(skip_locked=True, of=("self",))
                     .filter(status=C.PENDING, campaign__status=Campaign.Status.ACTIVE)
                     .exclude(attempts__state__in=[A.INITIATED, A.CONNECTED])[:BATCH])
        for c in fresh:
            c.attempt_count += 1
            CallAttempt.objects.create(contact=c, attempt_number=c.attempt_count, next_dispatch_at=now)
        Contact.objects.bulk_update(fresh, ["attempt_count"])
        due = list(CallAttempt.objects.select_for_update(skip_locked=True, of=("self",)).filter(
            state=A.INITIATED, started_at__isnull=True, next_dispatch_at__lte=now,
            contact__campaign__status=Campaign.Status.ACTIVE)[:BATCH])
        for a in due:
            a.next_dispatch_at = now + LEASE  # lease: a lost enqueue or worker is retried when it expires
        CallAttempt.objects.bulk_update(due, ["next_dispatch_at"])
    for a in due:
        dial_attempt.delay(str(a.pk))


@shared_task(queue="dial")
def dial_attempt(attempt_id):
    now = timezone.now()
    with transaction.atomic():
        attempt = (CallAttempt.objects.select_for_update(skip_locked=True, of=("self", "contact"))
                   .select_related("contact__campaign__retry_policy", "contact__campaign__agent_config")
                   .filter(pk=attempt_id, state=A.INITIATED, started_at__isnull=True).first())
        if attempt is None:  # already dialed (redelivery), locked by another worker, or gone
            return
        contact, campaign = attempt.contact, attempt.contact.campaign
        if campaign.status != Campaign.Status.ACTIVE or campaign.dograh_workflow_uuid is None \
                or contact.status not in (C.PENDING, C.RETRY_SCHEDULED):
            return
        if is_suppressed(contact):  # checked here, not only at enqueue
            attempt.state, attempt.ended_at, contact.status = A.FAILED_TO_CONNECT, now, C.CLOSED
            attempt.save()
            contact.save()
            return
        if wait := _window_wait(now, campaign.retry_policy):
            attempt.next_dispatch_at = wait
            attempt.save()
            return
        with connection.cursor() as cur:  # serialises the capacity check across workers
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [DIAL_LOCK])
        if CallAttempt.objects.filter(Q(state=A.CONNECTED) | Q(state=A.INITIATED, started_at__isnull=False)
                                      ).count() >= settings.DOGRAH_EFFECTIVE_CONCURRENCY:
            return
        attempt.started_at, contact.status = now, C.DIALING  # DIAL_REQUESTED marker, committed before the trigger call
        attempt.save()
        contact.save()
        phone, model = contact.phone_number, campaign.agent_config.model_config_uuid
    try:
        started = DograhClient().start_call(StartCallRequest(
            workflow_uuid=str(campaign.dograh_workflow_uuid), phone_number=phone, attempt_id=str(attempt.pk),
            campaign_id=str(campaign.pk), contact_ref=str(contact.pk), model_config_uuid=str(model) if model else None))
    except DialOutcomeUnknown:
        log.error("dial outcome unknown", extra={"attempt_id": str(attempt.pk)})  # reconciler resolves; never redial
    except DograhError:
        with transaction.atomic():
            locked = (CallAttempt.objects.select_for_update(of=("self", "contact"))
                      .select_related("contact__campaign__retry_policy").get(pk=attempt.pk))
            fail_attempt(locked, "provider_error")
    else:
        CallAttempt.objects.filter(pk=attempt.pk, provider_run_id__isnull=True).update(provider_run_id=started.run_id)
