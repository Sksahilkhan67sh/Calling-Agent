import json
from datetime import time

import pytest
import requests
import responses
from django.utils import timezone
from rest_framework.test import APIClient

from apps.calls.models import CallAttempt
from apps.calls.tasks import reconcile_stuck
from apps.campaigns.models import Campaign
from apps.contacts.models import Contact
from apps.dialer.tasks import dial_attempt, dispatch_due
from apps.suppression.models import Suppression
from apps.webhooks.models import WebhookReceipt

from .test_campaigns import create

WF = "6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d"
TRIGGER = f"https://dograh.test/api/v1/public/agent/workflow/{WF}"
HOOK = "/webhooks/dograh/run-completed"
SECRET = {"HTTP_X_DOGRAH_WEBHOOK_SECRET": "test-webhook-secret-test-webhook-secret"}


def run_url(run_id):
    return f"https://dograh.test/api/v1/runs/{run_id}"


@pytest.fixture
def contact(api):
    c = Campaign.objects.get(pk=create(api("admin", "Admin"), "+14155550100").json()["id"])
    Campaign.objects.filter(pk=c.pk).update(status="active", dograh_workflow_uuid=WF)
    c.retry_policy.window_start, c.retry_policy.window_end = time(0, 0), time(23, 59, 59)
    c.retry_policy.save()
    return Contact.objects.get(campaign=c)


def attempts(contact):
    return list(CallAttempt.objects.filter(contact=contact).order_by("attempt_number"))


def run_body(attempt, status="completed", disposition="goal_met", **extra):
    return {"status": status, "initial_context": {"attempt_id": str(attempt.pk)},
            "gathered_context": {"call_disposition": disposition}, **extra}


def dial(run_id="r1"):
    responses.post(TRIGGER, json={"workflow_run_id": run_id})
    dispatch_due()


def hook(attempt, run_id="r1", headers=SECRET, **extra):
    return APIClient().post(HOOK, {"attempt_id": str(attempt.pk), "run_id": run_id, **extra}, format="json", **headers)


def triggers():
    return [c for c in responses.calls if c.request.url == TRIGGER]


@responses.activate
def test_dial_stores_run_id_and_marks_dialing(contact):
    dial()
    (a,), contact = attempts(contact), Contact.objects.get(pk=contact.pk)
    assert a.provider_run_id == "r1" and a.started_at and contact.status == "Dialing" and contact.attempt_count == 1
    body = json.loads(triggers()[0].request.body)
    assert body["initial_context"] == {"attempt_id": str(a.pk), "campaign_id": str(contact.campaign_id), "contact_ref": str(contact.pk)}
    assert body["phone_number"] == "+14155550100"


@responses.activate
def test_dispatch_twice_and_task_redelivery_dial_once(contact):
    dial()
    dispatch_due()
    dial_attempt(str(attempts(contact)[0].pk))
    assert len(triggers()) == 1 and len(attempts(contact)) == 1


@responses.activate
def test_crash_mid_dial_unknown_outcome_never_redials_and_webhook_adopts_run(contact):
    responses.post(TRIGGER, body=requests.exceptions.ReadTimeout())
    dispatch_due()
    (a,) = attempts(contact)
    assert a.started_at and a.provider_run_id is None
    dial_attempt(str(a.pk))
    CallAttempt.objects.filter(pk=a.pk).update(next_dispatch_at=timezone.now())
    dispatch_due()
    assert len(triggers()) == 1
    responses.get(run_url("lost"), json=run_body(a))
    assert hook(a, "lost").status_code == 200
    a.refresh_from_db()
    assert a.provider_run_id == "lost" and a.state == "EndedNormally"
    assert Contact.objects.get(pk=contact.pk).status == "Completed"


@responses.activate
def test_unknown_outcome_past_ceiling_is_left_alone_not_redialed(contact, settings):
    responses.post(TRIGGER, status=502)
    dispatch_due()
    CallAttempt.objects.update(started_at=timezone.now() - timezone.timedelta(days=1))
    reconcile_stuck()
    (a,) = attempts(contact)
    assert a.state == "Initiated" and len(triggers()) == 1


@responses.activate
def test_definite_trigger_rejection_schedules_retry(contact):
    responses.post(TRIGGER, status=422)
    dispatch_due()
    first, second = attempts(contact)
    assert first.state == "FailedToConnect" and first.connection_failure_reason == "provider_error"
    assert second.attempt_number == 2 and second.started_at is None
    assert 25 < (second.next_dispatch_at - timezone.now()).total_seconds() <= 30
    assert Contact.objects.get(pk=contact.pk).status == "RetryScheduled"


@responses.activate
def test_suppression_added_mid_wait_blocks_dial(contact):
    Campaign.objects.filter(pk=contact.campaign_id).update(status="paused")
    dispatch_due()
    Campaign.objects.filter(pk=contact.campaign_id).update(status="active")
    Suppression.objects.create(contact=contact, phone_hmac=contact.phone_hmac, reason="asked", source="manual_api")
    responses.post(TRIGGER, json={"workflow_run_id": "x"})
    dispatch_due()
    assert not triggers() and Contact.objects.get(pk=contact.pk).status == "Closed"
    assert attempts(contact)[0].state == "FailedToConnect"


@responses.activate
def test_suppression_by_number_catches_reimported_contact(contact, api):
    other = Campaign.objects.get(pk=create(api("admin", "Admin"), "+14155550100").json()["id"])
    Campaign.objects.filter(pk=other.pk).update(status="active", dograh_workflow_uuid=WF)
    Suppression.objects.create(contact=contact, phone_hmac=contact.phone_hmac, reason="asked", source="manual_api")
    Campaign.objects.filter(pk=contact.campaign_id).update(status="completed")
    dispatch_due()
    assert not triggers() and Contact.objects.get(campaign=other).status == "Closed"


@responses.activate
def test_inactive_campaign_unsynced_workflow_and_window_and_capacity(contact):
    Campaign.objects.filter(pk=contact.campaign_id).update(status="paused")
    dispatch_due()
    assert not attempts(contact)
    Campaign.objects.filter(pk=contact.campaign_id).update(status="active", dograh_workflow_uuid=None)
    dispatch_due()
    assert not triggers()
    rp = contact.campaign.retry_policy
    now = timezone.now().time()
    rp.window_start, rp.window_end = time((now.hour + 2) % 24, 0), time((now.hour + 3) % 24, 0)
    rp.save()
    Campaign.objects.filter(pk=contact.campaign_id).update(dograh_workflow_uuid=WF)
    CallAttempt.objects.update(next_dispatch_at=timezone.now())
    dispatch_due()
    (a,) = attempts(contact)
    assert not triggers() and a.started_at is None and a.next_dispatch_at > timezone.now()


@responses.activate
def test_concurrency_cap(contact, api, settings):
    settings.DOGRAH_EFFECTIVE_CONCURRENCY = 1
    other = Campaign.objects.get(pk=create(api("admin", "Admin"), "+14155550101").json()["id"])
    Campaign.objects.filter(pk=other.pk).update(status="active", dograh_workflow_uuid=WF)
    other.retry_policy.window_start, other.retry_policy.window_end = time(0, 0), time(23, 59, 59)
    other.retry_policy.save()
    dial()
    assert len(triggers()) == 1 and CallAttempt.objects.count() == 2


# --- webhooks ---------------------------------------------------------------

@responses.activate
def test_webhook_rejects_bad_credentials_and_payload(contact):
    dial()
    (a,) = attempts(contact)
    assert hook(a, headers={}).status_code == 401
    assert hook(a, headers={"HTTP_X_DOGRAH_WEBHOOK_SECRET": "wrong"}).status_code == 401
    assert APIClient().post(HOOK, {"run_id": "r1"}, format="json", **SECRET).status_code == 422
    assert APIClient().post(HOOK, {"attempt_id": "nope", "run_id": "r1"}, format="json", **SECRET).status_code == 422
    assert not WebhookReceipt.objects.exists()


@responses.activate
def test_previous_secret_accepted_during_rotation(contact, settings):
    dial()
    settings.DOGRAH_WEBHOOK_SECRET, settings.DOGRAH_WEBHOOK_SECRET_PREVIOUS = "new-secret-new-secret-new-secret!", SECRET["HTTP_X_DOGRAH_WEBHOOK_SECRET"]
    responses.get(run_url("r1"), json=run_body(attempts(contact)[0], "in-progress"))
    assert hook(attempts(contact)[0]).status_code == 200


@responses.activate
def test_duplicate_webhook_applies_once(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json=run_body(a))
    assert hook(a).status_code == 200 and hook(a).status_code == 200
    assert WebhookReceipt.objects.count() == 1 and WebhookReceipt.objects.get().status == "processed"
    assert len([c for c in responses.calls if c.request.url == run_url("r1")]) == 1
    a.refresh_from_db()
    assert a.state == "EndedNormally" and Contact.objects.get(pk=contact.pk).status == "Completed"


@responses.activate
def test_forged_webhook_cannot_assert_outcome_dograh_does_not_confirm(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json=run_body(a, "in-progress"))
    hook(a, call_status="completed", call_disposition="goal_met")
    a.refresh_from_db()
    assert a.state == "Initiated" and WebhookReceipt.objects.get().status == "received"


@responses.activate
def test_run_belonging_to_another_attempt_is_rejected(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json={"status": "completed", "initial_context": {"attempt_id": "00000000-0000-0000-0000-000000000000"}})
    hook(a)
    a.refresh_from_db()
    assert a.state == "Initiated" and WebhookReceipt.objects.get().status == "rejected"


@responses.activate
def test_run_id_that_differs_from_stored_run_is_rejected(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("other"), json=run_body(a))
    hook(a, "other")
    a.refresh_from_db()
    assert a.provider_run_id == "r1" and a.state == "Initiated" and WebhookReceipt.objects.get().status == "rejected"


@responses.activate
def test_unknown_attempt_is_rejected_without_state_change(contact):
    dial()
    ghost = CallAttempt(pk="11111111-1111-1111-1111-111111111111")
    responses.get(run_url("g"), json=run_body(ghost))
    assert hook(ghost, "g").status_code == 200
    assert WebhookReceipt.objects.get(run_id="g").status == "rejected"


@responses.activate
def test_pull_failure_leaves_receipt_for_redelivery_and_reconciler(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), status=500)
    with pytest.raises(Exception):
        hook(a)
    assert WebhookReceipt.objects.get().status == "received" and attempts(contact)[0].state == "Initiated"
    responses.replace(responses.GET, run_url("r1"), json=run_body(a))
    hook(a)
    assert WebhookReceipt.objects.get().status == "processed" and attempts(contact)[0].state == "EndedNormally"


# --- outcomes, terminal guard, reconciler -----------------------------------

@pytest.mark.parametrize("status,reason", [("busy", "busy"), ("no-answer", "no_answer"), ("failed", "provider_error"),
                                           ("error", "provider_error"), ("canceled", "provider_error")])
@responses.activate
def test_never_connected_outcomes_schedule_retry(contact, status, reason):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json=run_body(a, status))
    hook(a)
    first, second = attempts(contact)
    assert first.state == "FailedToConnect" and first.connection_failure_reason == reason
    assert Contact.objects.get(pk=contact.pk).status == "RetryScheduled" and second.attempt_number == 2


@responses.activate
def test_retries_exhaust_to_closed_with_spacing_from_policy(contact):
    Contact.objects.filter(pk=contact.pk).update(attempt_count=2)
    CallAttempt.objects.create(contact=contact, attempt_number=2, next_dispatch_at=timezone.now())
    Contact.objects.filter(pk=contact.pk).update(status="RetryScheduled")
    responses.post(TRIGGER, json={"workflow_run_id": "r9"})
    dispatch_due()
    a = attempts(contact)[0]
    responses.get(run_url("r9"), json=run_body(a, "busy"))
    hook(a, "r9")
    assert Contact.objects.get(pk=contact.pk).status == "RetryScheduled" and len(attempts(contact)) == 2
    CallAttempt.objects.filter(attempt_number=3).update(next_dispatch_at=timezone.now())
    responses.replace(responses.POST, TRIGGER, json={"workflow_run_id": "r10"})
    dispatch_due()
    last = attempts(contact)[-1]
    responses.get(run_url("r10"), json=run_body(last, "busy"))
    hook(last, "r10")
    assert Contact.objects.get(pk=contact.pk).status == "Closed" and len(attempts(contact)) == 2


@responses.activate
def test_unmapped_completion_is_a_retryable_drop_not_success(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json=run_body(a, "completed", "something_new"))
    hook(a)
    a.refresh_from_db()
    assert a.state == "DroppedMidCall" and a.disconnect_reason == "unknown"
    assert Contact.objects.get(pk=contact.pk).status == "Disconnected"


@responses.activate
def test_terminal_attempt_cannot_change_on_replayed_or_conflicting_run(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json=run_body(a))
    hook(a)
    responses.replace(responses.GET, run_url("r1"), json=run_body(a, "completed", "something_new"))
    WebhookReceipt.objects.all().delete()
    hook(a)
    a.refresh_from_db()
    assert a.state == "EndedNormally" and Contact.objects.get(pk=contact.pk).status == "Completed"


@responses.activate
def test_lost_webhook_recovered_by_reconciler(contact):
    dial()
    (a,) = attempts(contact)
    responses.get(run_url("r1"), json=run_body(a, "in-progress"))
    reconcile_stuck()
    assert attempts(contact)[0].state == "Initiated"
    CallAttempt.objects.update(started_at=timezone.now() - timezone.timedelta(seconds=901))
    responses.replace(responses.GET, run_url("r1"), json=run_body(a))
    reconcile_stuck()
    a.refresh_from_db()
    assert a.state == "EndedNormally" and Contact.objects.get(pk=contact.pk).status == "Completed"
    reconcile_stuck()
    assert len([c for c in responses.calls if c.request.url == run_url("r1")]) == 1  # terminal attempts are not pulled again


@responses.activate
def test_reconciler_pull_error_does_not_abort_other_attempts(contact):
    dial()
    CallAttempt.objects.update(started_at=timezone.now() - timezone.timedelta(days=1))
    responses.get(run_url("r1"), status=500)
    reconcile_stuck()
    assert attempts(contact)[0].state == "Initiated"
