"""Append-only audit trail (Security-Architecture §9, Database-Design §2.15).

Immutability is enforced in three independent layers; each is tested on its own:
1. model layer (this file): no update, no delete, no queryset update/delete;
2. database layer: triggers raising on UPDATE, DELETE and TRUNCATE (migration 0002);
3. privilege layer: the application role holds only INSERT and SELECT (deploy/sql/roles.sql, P2-17).

There are deliberately no foreign keys: audit rows outlive the users, clients and objects they describe.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.db.models.functions import Now


class AuditImmutableError(RuntimeError):
    """Raised on any attempt to modify or delete an audit event."""


class ActorType(models.TextChoices):
    USER = "user"
    API_CLIENT = "api_client"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


class Outcome(models.TextChoices):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise AuditImmutableError("audit events cannot be updated")

    def bulk_update(self, *args: Any, **kwargs: Any) -> int:
        raise AuditImmutableError("audit events cannot be updated")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AuditImmutableError("audit events cannot be deleted")

    def _raw_delete(self, using: Any) -> int:
        raise AuditImmutableError("audit events cannot be deleted")

    def bulk_create(self, objs: Any, *args: Any, **kwargs: Any) -> list[AuditEvent]:
        if kwargs.get("update_conflicts"):
            raise AuditImmutableError("audit events cannot be upserted")
        return super().bulk_create(objs, *args, **kwargs)


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Server-set (database clock); callers cannot choose it.
    occurred_at = models.DateTimeField(db_default=Now(), editable=False)
    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_label = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.SUCCESS)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    metadata = models.JSONField(default=dict)

    objects = AuditQuerySet.as_manager()

    class Meta:
        db_table = "audit_event"
        default_permissions = ("view",)
        indexes = [
            models.Index(fields=["occurred_at"], name="audit_occurred_idx"),
            models.Index(fields=["actor_id", "occurred_at"], name="audit_actor_idx"),
            models.Index(fields=["object_type", "object_id", "occurred_at"], name="audit_object_idx"),
            models.Index(fields=["action", "occurred_at"], name="audit_action_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_type}:{self.actor_label or self.actor_id}"

    def save(self, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AuditImmutableError("audit events cannot be modified")
        super().save(**kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AuditImmutableError("audit events cannot be deleted")
