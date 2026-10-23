import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.voice_runtime.client import DograhClient, DograhError

from .models import CallAttempt
from .services import apply_run

log = logging.getLogger(__name__)


@shared_task(queue="recovery")
def reconcile_stuck():
    """Resolve attempts whose webhook never arrived by pulling the run (Dograh Integration §5.4)."""
    cutoff = timezone.now() - timedelta(seconds=settings.RECONCILE_CEILING_SECONDS)
    stuck = CallAttempt.objects.filter(
        Q(state=CallAttempt.State.CONNECTED) | Q(state=CallAttempt.State.INITIATED, started_at__isnull=False),
        started_at__lt=cutoff)
    for attempt in stuck:
        if attempt.provider_run_id is None:
            # [verify] runs cannot be listed by initial_context, so never redial an unknown outcome; surface it instead
            log.error("dial outcome unknown past ceiling", extra={"attempt_id": str(attempt.pk)})
            continue
        try:
            apply_run(attempt.pk, DograhClient().get_run(attempt.provider_run_id))
        except DograhError:
            log.exception("reconcile pull failed", extra={"attempt_id": str(attempt.pk)})
