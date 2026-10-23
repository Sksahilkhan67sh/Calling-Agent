from celery import shared_task
from django.db import transaction

from apps.calls.models import CallAttempt
from apps.contacts.models import Contact
from apps.recovery.models import WorkingMemorySnapshot

from .models import Analysis, FinalOutput
from .scoring import VERSION, score

TERMINAL = (Contact.Status.COMPLETED, Contact.Status.COMPLETED_PARTIAL)


@shared_task(queue="analysis")
def analyze_attempt(attempt_id):
    """Idempotent: exactly one final_output per contact, only from a terminal contact state."""
    with transaction.atomic():
        attempt = CallAttempt.objects.select_related("contact__campaign__agent_config").get(pk=attempt_id)
        contact = Contact.objects.select_for_update().get(pk=attempt.contact_id)
        if contact.status not in TERMINAL or FinalOutput.objects.filter(contact=contact).exists():
            return
        snapshot = WorkingMemorySnapshot.objects.filter(attempt__contact=contact).order_by("-snapshotted_at").first()
        memory = snapshot.memory if snapshot else {}
        result = score(memory, attempt.contact.campaign.agent_config.required_entity_fields,
                       partial=contact.status == Contact.Status.COMPLETED_PARTIAL,
                       suppressed=bool(snapshot and snapshot.requires_suppression))
        entities = memory.get("captured_entities") or {}
        # [verify] summary/sentiment/suggestions/buying-intent come from Dograh gathered_context when present; none are generated here
        feedback = {"key_points": memory.get("key_points", []), "sentiment": memory.get("sentiment"),
                    "objections": [o.get("objection") for o in memory.get("objections_raised") or []],
                    "suggestions": memory.get("suggestions", [])}
        disposition = ""
        Analysis.objects.create(
            attempt=attempt, interest_classification=result["interest_classification"], lead_score=result["lead_score"],
            qualification_level=result["qualification_level"], temperature_tag=result["temperature_tag"],
            conversion_probability=result["conversion_probability"], score_confidence=result["score_confidence"],
            feedback=feedback, disposition=disposition, scoring_version=VERSION)
        FinalOutput.objects.create(
            contact=contact, source_attempt=attempt, feedback=feedback,
            transcript_ref=getattr(attempt, "transcript", None), recording_ref=getattr(attempt, "recording", None),
            interest_detection={"interested": result["interest_classification"] == "interested",
                                "follow_up_detected": entities.get("follow_up_preference") not in (None, "", "not_captured"),
                                "buying_intent": memory.get("buying_intent"), "intent_confidence": memory.get("intent_confidence")},
            lead_score_summary={k: result[k] for k in ("lead_score", "qualification_level", "temperature_tag",
                                                       "conversion_probability", "score_confidence")},
            call_summary={"summary": memory.get("call_summary"), "next_action_suggestion": memory.get("next_action"),
                          "disposition": disposition, "tags": []})


@shared_task(queue="analysis")
def sweep_unanalyzed():
    """Backstop for a lost enqueue: terminal contacts without a final_output."""
    for contact in Contact.objects.filter(status__in=TERMINAL, final_output__isnull=True):
        last = contact.attempts.order_by("-attempt_number").first()
        if last:
            analyze_attempt.delay(str(last.pk))
