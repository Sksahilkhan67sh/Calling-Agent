import uuid

from django.db import models


class WebhookReceipt(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received"
        PROCESSED = "processed"
        REJECTED = "rejected"  # verify-by-pull mismatch

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=16)
    run_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=32)
    claimed_attempt_id = models.UUIDField()
    payload_hash = models.BinaryField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "run_id", "event_type"], name="webhook_receipt_unique")]
