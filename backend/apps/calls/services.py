import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.contacts.models import Contact

from .models import CallAttempt

log = logging.getLogger(__name__)
A, C = CallAttempt.State, Contact.Status

# Call State Machine §3.2 / §2.2; call_failed is decided by the retry rules in _fail
ATTEMPT_NEXT = {(A.INITIATED, "call_connected"): A.CONNECTED, (A.CONNECTED, "call_ended_normally"): A.ENDED_NORMALLY,
                (A.CONNECTED, "call_disconnected"): A.DROPPED_MID_CALL}
CONTACT_NEXT = {(C.DIALING, "call_connected"): C.IN_CONVERSATION, (C.IN_CONVERSATION, "call_ended_normally"): C.COMPLETED,
                (C.IN_CONVERSATION, "call_disconnected"): C.DISCONNECTED}
# Dograh Integration §5.2; carrier-specific invalid_number/rejected are [verify], so failures stay retryable provider_error
FAILURE_REASON = {"busy": "busy", "no-answer": "no_answer", "failed": "provider_error", "error": "provider_error",
                  "canceled": "provider_error"}
NO_RETRY = {"rejected", "invalid_number"}


def _step(attempt, event):
    contact = attempt.contact
    nxt = ATTEMPT_NEXT.get((attempt.state, event))
    cnext = CONTACT_NEXT.get((contact.status, event))
    if nxt is None or cnext is None:
        log.warning("illegal transition", extra={"attempt_id": str(attempt.pk), "event": event,
                                                 "attempt_state": attempt.state, "contact_status": contact.status})
        return False
    attempt.state, contact.status = nxt, cnext
    return True


def fail_attempt(attempt, reason):
    """Dialing → call_failed. Caller holds row locks on attempt and contact inside transaction.atomic."""
    contact, now = attempt.contact, timezone.now()
    if attempt.state != A.INITIATED or contact.status != C.DIALING:
        log.warning("illegal transition", extra={"attempt_id": str(attempt.pk), "event": "call_failed"})
        return
    attempt.state, attempt.connection_failure_reason, attempt.ended_at = A.FAILED_TO_CONNECT, reason, now
    policy, retries_so_far = contact.campaign.retry_policy, contact.attempt_count - 1
    if reason not in NO_RETRY and policy.never_connected_rules.get(reason) and retries_so_far < policy.max_retries:
        delay = policy.retry_spacing_seconds[retries_so_far]  # serializer guarantees one value per retry
        contact.attempt_count += 1
        CallAttempt.objects.create(contact=contact, attempt_number=contact.attempt_count,
                                   next_dispatch_at=now + timedelta(seconds=delay))
        contact.status = C.RETRY_SCHEDULED
    else:
        contact.status = C.CLOSED
    attempt.save()
    contact.save()


def apply_run(attempt_id, run):
    """Feed a pulled Dograh run into the state machine. Returns 'applied', 'pending' or 'rejected'."""
    if not run.terminal:
        return "pending"
    if run.initial_context.get("attempt_id") != str(attempt_id):
        log.error("run does not belong to claimed attempt", extra={"attempt_id": str(attempt_id), "run_id": run.run_id})
        return "rejected"
    with transaction.atomic():
        attempt = (CallAttempt.objects.select_for_update(of=("self", "contact"))
                   .select_related("contact__campaign__retry_policy").filter(pk=attempt_id).first())
        if attempt is None or attempt.provider_run_id not in (None, run.run_id):
            log.error("run/attempt mismatch", extra={"attempt_id": str(attempt_id), "run_id": run.run_id})
            return "rejected"
        if attempt.state not in (A.INITIATED, A.CONNECTED):
            log.info("run for terminal attempt ignored", extra={"attempt_id": str(attempt_id), "run_id": run.run_id})
            return "applied"
        attempt.provider_run_id = run.run_id  # also adopts the run when a crash lost the trigger response
        if run.status in FAILURE_REASON:
            fail_attempt(attempt, FAILURE_REASON[run.status])
            return "applied"
        normal = run.gathered_context.get("call_disposition") in settings.DOGRAH_COMPLETED_DISPOSITIONS
        if not normal:  # unknown outcome is treated as a drop (retryable), never as success
            log.warning("unmapped run outcome", extra={"attempt_id": str(attempt_id), "run_id": run.run_id})
            attempt.disconnect_reason = "unknown"
        if attempt.state == A.INITIATED:
            _step(attempt, "call_connected")
        _step(attempt, "call_ended_normally" if normal else "call_disconnected")
        attempt.ended_at = timezone.now()
        attempt.save()
        attempt.contact.save()
    return "applied"
