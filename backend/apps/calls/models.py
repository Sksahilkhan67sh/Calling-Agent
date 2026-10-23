import uuid

from django.db import models
from django.db.models import Q

from apps.campaigns.models import MID_CALL_REASONS, NEVER_CONNECTED_REASONS
from apps.contacts.models import Contact
from apps.core.crypto import decrypt

RECORDING_CONSENT = ("granted", "denied", "unclear", "not_applicable")


class CallAttempt(models.Model):
    class State(models.TextChoices):
        INITIATED = "Initiated"
        CONNECTED = "Connected"
        FAILED_TO_CONNECT = "FailedToConnect"
        DROPPED_MID_CALL = "DroppedMidCall"
        ENDED_NORMALLY = "EndedNormally"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveIntegerField()
    state = models.CharField(max_length=20, choices=State.choices, default=State.INITIATED)
    connection_failure_reason = models.CharField(
        max_length=20, choices=[(r, r) for r in NEVER_CONNECTED_REASONS], null=True, blank=True)
    disconnect_reason = models.CharField(
        max_length=20, choices=[(r, r) for r in MID_CALL_REASONS], null=True, blank=True)
    recording_consent = models.CharField(max_length=14, choices=[(c, c) for c in RECORDING_CONSENT], null=True, blank=True)
    reconnect_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reconnects")
    provider = models.CharField(max_length=16, default="dograh")
    provider_run_id = models.CharField(max_length=64, null=True, blank=True)
    next_dispatch_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)  # set with the DIAL_REQUESTED marker, before the trigger call
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contact", "attempt_number"], name="attempt_unique_number_per_contact"),
            models.UniqueConstraint(fields=["provider", "provider_run_id"], name="attempt_unique_provider_run",
                                    condition=Q(provider_run_id__isnull=False)),
        ]
        indexes = [models.Index(fields=["state", "next_dispatch_at"])]


class DisconnectEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(CallAttempt, on_delete=models.CASCADE, related_name="disconnect_events")
    reason = models.CharField(max_length=20, choices=[(r, r) for r in MID_CALL_REASONS])
    occurred_at = models.DateTimeField()
    retry_approved = models.BooleanField(null=True)  # null until evaluated


class Transcript(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.OneToOneField(CallAttempt, on_delete=models.CASCADE, related_name="transcript")
    is_partial = models.BooleanField()
    content_encrypted = models.BinaryField()
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def content(self):
        return decrypt(self.content_encrypted)


class RecordingRef(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.OneToOneField(CallAttempt, on_delete=models.CASCADE, related_name="recording")
    storage_path = models.CharField(max_length=255)
    duration_seconds = models.PositiveIntegerField()
