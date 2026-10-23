import json

import boto3
import pytest
import responses
from moto import mock_aws
from django.utils import timezone

from apps.analysis.models import Analysis, FinalOutput
from apps.analysis.scoring import score
from apps.analysis.tasks import analyze_attempt, sweep_unanalyzed
from apps.calls.models import CallAttempt, DisconnectEvent, RecordingRef, Transcript
from apps.contacts.models import Contact
from apps.dialer.tasks import dispatch_due
from apps.recovery.models import WorkingMemorySnapshot
from apps.suppression.models import Suppression

from .test_calling_engine import TRIGGER, attempts, contact, dial, hook, run_url, triggers  # noqa: F401

REC, TRN = "https://artifacts.dograh.test/rec.mp3", "https://artifacts.dograh.test/t.txt"
MEMORY = {"captured_entities": {"interest_level": "interested", "decision_maker_status": "sole"},
          "objections_raised": [{"objection": "price", "addressed": True}], "next_action": "confirm_and_close",
          "last_agent_utterance": "SECRET-UTTERANCE"}


def body(attempt, disposition="goal_met", status="completed", **ctx):
    return {"status": status, "initial_context": {"attempt_id": str(attempt.pk)}, "recording_url": REC, "transcript_url": TRN,
            "cost_info": {"call_duration_seconds": 31},
            "gathered_context": {"call_disposition": disposition, **MEMORY, **ctx}}


@pytest.fixture
def bucket():
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="test-recordings")
        yield boto3.client("s3")


def drop_first_call(contact, **ctx):
    dial("r1")
    a = attempts(contact)[0]
    responses.get(run_url("r1"), json=body(a, "dropped", **ctx))
    responses.get(TRN, body="agent: hi")
    responses.get(REC, body=b"audio")
    hook(a, "r1")
    return a


@responses.activate
def test_drop_saves_state_before_decision_then_reconnects_with_memory(contact, bucket):
    a = drop_first_call(contact, recording_consent="granted")
    a.refresh_from_db()
    ev = DisconnectEvent.objects.get(attempt=a)
    snap = WorkingMemorySnapshot.objects.get(attempt=a)
    assert a.state == "DroppedMidCall" and ev.retry_approved is True and snap.disconnect_count == 1
    assert snap.memory["last_agent_utterance"] == "SECRET-UTTERANCE" and b"SECRET" not in bytes(snap.memory_encrypted)
    assert Transcript.objects.get(attempt=a).is_partial and Transcript.objects.get(attempt=a).content == "agent: hi"
    assert Contact.objects.get(pk=contact.pk).status == "RetryScheduled"
    _, re = attempts(contact)
    assert re.reconnect_of_id == a.pk and 25 < (re.next_dispatch_at - timezone.now()).total_seconds() <= 30

    CallAttempt.objects.filter(pk=re.pk).update(next_dispatch_at=timezone.now())
    responses.replace(responses.POST, TRIGGER, json={"workflow_run_id": "r2"})
    dispatch_due()
    sent = json.loads(triggers()[-1].request.body)["initial_context"]
    assert sent["resume_memory"]["last_agent_utterance"] == "SECRET-UTTERANCE" and sent["attempt_id"] == str(re.pk)
    assert Contact.objects.get(pk=contact.pk).status == "Reconnecting"

    re.refresh_from_db()
    responses.get(run_url("r2"), json=body(re, recording_consent="granted"))
    hook(re, "r2")
    assert Contact.objects.get(pk=contact.pk).status == "Completed"
    fo = FinalOutput.objects.get(contact=contact)
    assert fo.source_attempt_id == re.pk and fo.lead_score_summary["lead_score"] >= 80
    assert RecordingRef.objects.filter(attempt=re).exists()


@responses.activate
def test_retry_not_approved_or_exhausted_closes_partial_with_partial_confidence(contact, bucket):
    rp = contact.campaign.retry_policy
    rp.mid_call_rules["unknown"] = False
    rp.save()
    a = drop_first_call(contact)
    assert Contact.objects.get(pk=contact.pk).status == "CompletedPartial"
    assert DisconnectEvent.objects.get(attempt=a).retry_approved is False and len(attempts(contact)) == 1
    fo = FinalOutput.objects.get(contact=contact)
    assert fo.lead_score_summary["score_confidence"] == "partial" and Analysis.objects.get(attempt=a)


@responses.activate
def test_failed_reconnect_reenters_disconnect_path(contact, bucket):
    drop_first_call(contact)
    _, re = attempts(contact)
    CallAttempt.objects.filter(pk=re.pk).update(next_dispatch_at=timezone.now())
    responses.replace(responses.POST, TRIGGER, status=422)
    dispatch_due()
    re.refresh_from_db()
    assert re.state == "FailedToConnect" and DisconnectEvent.objects.filter(attempt=re).count() == 1
    assert Contact.objects.get(pk=contact.pk).status == "RetryScheduled" and len(attempts(contact)) == 3
    assert WorkingMemorySnapshot.objects.get(attempt=re).memory["last_agent_utterance"] == "SECRET-UTTERANCE"


@responses.activate
def test_suppression_request_in_call_blocks_retry_and_forces_unqualified(contact, bucket):
    drop_first_call(contact, requires_suppression=True)
    assert Suppression.objects.get(contact=contact).source == "agent_in_call"
    assert Contact.objects.get(pk=contact.pk).status == "CompletedPartial"
    assert FinalOutput.objects.get(contact=contact).lead_score_summary["qualification_level"] == "Unqualified"


@responses.activate
def test_artifact_failure_blocks_state_change_until_saved(contact, bucket):
    dial("r1")
    a = attempts(contact)[0]
    responses.get(run_url("r1"), json=body(a))
    responses.get(TRN, status=500)
    with pytest.raises(Exception):
        hook(a, "r1")
    a.refresh_from_db()
    assert a.state == "Initiated" and not DisconnectEvent.objects.exists()
    responses.replace(responses.GET, TRN, body="ok")
    hook(a, "r1")
    assert attempts(contact)[0].state == "EndedNormally"


@pytest.mark.parametrize("consent", [None, "denied", "unclear", "not_applicable"])
@responses.activate
def test_recording_never_stored_without_explicit_grant(contact, bucket, consent):
    dial("r1")
    a = attempts(contact)[0]
    responses.get(run_url("r1"), json=body(a, **({"recording_consent": consent} if consent else {})))
    responses.get(TRN, body="t")
    hook(a, "r1")
    assert not RecordingRef.objects.exists() and bucket.list_objects_v2(Bucket="test-recordings")["KeyCount"] == 0
    assert not [c for c in responses.calls if c.request.url == REC]
    a.refresh_from_db()
    assert a.recording_consent == consent


@responses.activate
def test_recording_granted_is_encrypted_in_private_bucket(contact, bucket):
    dial("r1")
    a = attempts(contact)[0]
    responses.get(run_url("r1"), json=body(a, recording_consent="granted"))
    responses.get(TRN, body="t")
    responses.get(REC, body=b"audio")
    hook(a, "r1")
    obj = bucket.get_object(Bucket="test-recordings", Key=f"recordings/{a.pk}")
    assert obj["Body"].read() == b"audio" and obj["ServerSideEncryption"] == "AES256"
    assert RecordingRef.objects.get(attempt=a).duration_seconds == 31


@responses.activate
def test_analysis_is_idempotent_terminal_only_and_swept(contact, bucket):
    dial("r1")
    a = attempts(contact)[0]
    analyze_attempt(str(a.pk))
    assert not FinalOutput.objects.exists()
    responses.get(run_url("r1"), json=body(a))
    responses.get(TRN, body="t")
    hook(a, "r1")
    analyze_attempt(str(a.pk))
    analyze_attempt(str(a.pk))
    assert FinalOutput.objects.count() == 1 and Analysis.objects.count() == 1
    FinalOutput.objects.all().delete()
    Analysis.objects.all().delete()
    sweep_unanalyzed()
    assert FinalOutput.objects.count() == 1


def test_worked_example_scores_95_and_partial_without_interest_is_low():
    memory = {**MEMORY, "turns": [{"utterance": "yes that sounds fine to me"}] * 8 + [{"utterance": "ok"}] * 2}
    r = score(memory, ["interest_level", "decision_maker_status"], partial=False, suppressed=False)
    assert r["lead_score"] == 95 and r["temperature_tag"] == "Hot" and r["qualification_level"] == "Highly Qualified"
    low = score({"captured_entities": {}}, ["interest_level"], partial=True, suppressed=False)
    assert low["lead_score"] == 0 and low["score_confidence"] == "partial" and low["temperature_tag"] == "Cold"
    assert score({"captured_entities": {"interest_level": "not_interested"}}, [], partial=False, suppressed=False)["lead_score"] == 25
