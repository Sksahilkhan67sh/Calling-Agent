import json
import tempfile
from datetime import timedelta
from io import BytesIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.calls.models import RECORDING_CONSENT, CallAttempt, DisconnectEvent, RecordingRef, Transcript
from apps.contacts.models import Contact
from apps.core.crypto import encrypt
from apps.voice_runtime.client import DograhClient, DograhError

from .models import WorkingMemorySnapshot

RETRYABLE = (DograhError, BotoCoreError, ClientError)
# [verify] Dograh gathered_context key names are not in the docs; these follow Memory Specification §2 / Prompt Specification §4
MEMORY_KEYS = ("captured_entities", "script_progress", "objections_raised", "last_agent_utterance", "next_action", "turns",
               "call_summary", "key_points", "sentiment", "suggestions", "buying_intent", "intent_confidence")


def is_normal(run):
    return run.gathered_context.get("call_disposition") in settings.DOGRAH_COMPLETED_DISPOSITIONS


def s3():
    return boto3.client("s3", endpoint_url=settings.OBJECT_STORAGE_ENDPOINT_URL,
                        config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2}))


def save_artifacts(attempt_id, run):
    """Copy transcript/recording to private storage before any state change; Dograh URLs are time-limited bearer credentials."""
    attempt = CallAttempt.objects.filter(
        Q(provider_run_id__isnull=True) | Q(provider_run_id=run.run_id),
        pk=attempt_id, state__in=[CallAttempt.State.INITIATED, CallAttempt.State.CONNECTED]).first()
    if attempt is None or run.status != "completed":
        return
    if run.transcript_url and not Transcript.objects.filter(attempt=attempt).exists():
        buf = BytesIO()
        DograhClient().download_artifact(run.transcript_url, buf)
        Transcript.objects.get_or_create(attempt=attempt, defaults={
            "is_partial": not is_normal(run), "content_encrypted": encrypt(buf.getvalue().decode("utf-8", "replace"))})
    # Only an explicit grant allows keeping audio; absent/unclear/denied never default to granted (Recording Consent §6)
    if run.recording_url and run.gathered_context.get("recording_consent") == "granted" \
            and not RecordingRef.objects.filter(attempt=attempt).exists():
        key = f"recordings/{attempt.pk}"
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as f:
            DograhClient().download_artifact(run.recording_url, f)
            f.seek(0)
            s3().upload_fileobj(f, settings.OBJECT_STORAGE_BUCKET, key, ExtraArgs={"ServerSideEncryption": "AES256"})
        RecordingRef.objects.get_or_create(attempt=attempt, defaults={
            "storage_path": key, "duration_seconds": int(run.duration_seconds or 0)})


def save_snapshot(attempt, ctx):
    prior = WorkingMemorySnapshot.objects.filter(attempt__contact=attempt.contact).order_by("-snapshotted_at").first()
    memory = {k: ctx[k] for k in MEMORY_KEYS if k in ctx} or (prior.memory if prior else {})
    consent = ctx.get("recording_consent")
    return WorkingMemorySnapshot.objects.create(
        attempt=attempt, memory_encrypted=encrypt(json.dumps(memory)),
        disconnect_count=DisconnectEvent.objects.filter(attempt__contact=attempt.contact).count(),
        requires_suppression=ctx.get("requires_suppression") is True or bool(prior and prior.requires_suppression),
        recording_consent=consent if consent in RECORDING_CONSENT else None)


def handle_disconnect(attempt, ctx, reason):
    """Disconnected → save state → retry decision. Runs inside apply_run's transaction, so snapshot and decision commit together."""
    contact, now = attempt.contact, timezone.now()
    policy = contact.campaign.retry_policy
    event = DisconnectEvent.objects.create(attempt=attempt, reason=reason, occurred_at=now)
    snapshot = save_snapshot(attempt, ctx)
    retries_so_far = contact.attempt_count - 1
    event.retry_approved = bool(policy.mid_call_rules.get(reason)) and retries_so_far < policy.max_retries \
        and not snapshot.requires_suppression
    event.save(update_fields=["retry_approved"])
    if event.retry_approved:
        contact.attempt_count += 1
        CallAttempt.objects.create(
            contact=contact, attempt_number=contact.attempt_count, reconnect_of=attempt,
            next_dispatch_at=now + timedelta(seconds=policy.retry_spacing_seconds[retries_so_far]))
        contact.status = Contact.Status.RETRY_SCHEDULED
    else:
        contact.status = Contact.Status.COMPLETED_PARTIAL
    contact.save()


def resume_vars(attempt):
    """Reconnect is a new run seeded with the saved memory (Dograh Integration §5.3)."""
    snapshot = WorkingMemorySnapshot.objects.filter(attempt__contact=attempt.contact).order_by("-snapshotted_at").first()
    return {"resume_memory": snapshot.memory, "resume_of_attempt": str(attempt.reconnect_of_id)} if snapshot else {}
