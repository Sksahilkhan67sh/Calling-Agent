import uuid

from django.db import models
from django.db.models import Q

from apps.campaigns.models import MID_CALL_REASONS, NEVER_CONNECTED_REASONS
from apps.contacts.models import Contact


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
