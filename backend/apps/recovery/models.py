import json
import uuid

from django.db import models

from apps.calls.models import RECORDING_CONSENT, CallAttempt
from apps.core.crypto import decrypt


class WorkingMemorySnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(CallAttempt, on_delete=models.CASCADE, related_name="snapshots")
    memory_encrypted = models.BinaryField()  # entities, objections, last utterance etc. are Restricted PII
    disconnect_count = models.PositiveIntegerField(default=0)
    requires_suppression = models.BooleanField(default=False)
    recording_consent = models.CharField(max_length=14, choices=[(c, c) for c in RECORDING_CONSENT], null=True, blank=True)
    schema_version = models.CharField(max_length=8, default="1")
    snapshotted_at = models.DateTimeField(auto_now_add=True)

    @property
    def memory(self):
        return json.loads(decrypt(self.memory_encrypted))
