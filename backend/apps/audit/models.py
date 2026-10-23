import uuid

from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.CharField(max_length=150)  # username or service name; no FK so it outlives the user
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    source_ip = models.CharField(max_length=45, null=True)

    class Meta:
        db_table = "audit_event"
        indexes = [models.Index(fields=["object_type", "object_id"])]
