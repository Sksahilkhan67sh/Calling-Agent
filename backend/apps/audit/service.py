"""``audit.record`` and ``audited``: write the audit event in the same transaction as the change.

Fail closed: ``record`` must run inside ``transaction.atomic()``, so if the audit insert fails the
change it describes is rolled back with it. ``ATOMIC_REQUESTS`` is off, so callers open the
transaction explicitly, usually through ``audited``.
"""

from __future__ import annotations

import getpass
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from django.db import DEFAULT_DB_ALIAS, transaction

from apps.audit.actions import ACTIONS
from apps.audit.context import get_request_info
from apps.audit.models import ActorType, AuditEvent, Outcome
from apps.audit.redaction import redact_payload
from apps.core.logging import get_context

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class AuditError(RuntimeError):
    """The audit event cannot be written; the surrounding change must not proceed."""


@dataclass(frozen=True)
class Actor:
    type: str
    id: uuid.UUID | None = None
    label: str = ""

    @classmethod
    def user(cls, user: Any) -> Actor:
        return cls(ActorType.USER, user.pk, user.email)

    @classmethod
    def api_client(cls, client_id: uuid.UUID, name: str) -> Actor:
        return cls(ActorType.API_CLIENT, client_id, name)

    @classmethod
    def system(cls, label: str) -> Actor:
        return cls(ActorType.SYSTEM, None, label)

    @classmethod
    def cli(cls) -> Actor:
        """A management command run by an operating-system user: ``system:cli:<os-user>``."""
        try:
            name = getpass.getuser()
        except Exception:  # noqa: BLE001 - no passwd entry in some containers; still must be recordable
            name = "unknown"
        return cls(ActorType.SYSTEM, None, f"system:cli:{name}")

    @classmethod
    def anonymous(cls, label: str = "") -> Actor:
        return cls(ActorType.ANONYMOUS, None, label)


def _clean(text: str, limit: int) -> str:
    return _CONTROL_CHARS.sub("", text)[:limit]


def record(
    *,
    action: str,
    actor: Actor,
    object_type: str = "",
    object_id: object = None,
    before: Any = None,
    after: Any = None,
    outcome: str = Outcome.SUCCESS,
    metadata: dict[str, Any] | None = None,
    using: str = DEFAULT_DB_ALIAS,
) -> AuditEvent:
    if action not in ACTIONS:
        raise AuditError(f"Unknown audit action: {action!r}")
    if outcome not in Outcome.values:
        raise AuditError(f"Unknown audit outcome: {outcome!r}")
    if not transaction.get_connection(using).in_atomic_block:
        raise AuditError("audit.record() must run inside transaction.atomic() (use audited())")
    info = get_request_info()
    return AuditEvent.objects.using(using).create(
        actor_type=actor.type,
        actor_id=actor.id,
        actor_label=_clean(actor.label, 254),
        action=action,
        object_type=_clean(object_type, 64),
        object_id=_clean("" if object_id is None else str(object_id), 64),
        before=redact_payload(before),
        after=redact_payload(after),
        outcome=outcome,
        source_ip=info.source_ip,
        request_id=_clean(get_context().get("request_id", ""), 64),
        user_agent=_clean(info.user_agent, 256),
        metadata=redact_payload(metadata or {}),
    )


@dataclass
class AuditScope:
    """Yielded by ``audited``: set ``after`` (and ``object_id`` once known) inside the block."""

    action: str
    actor: Actor
    object_type: str = ""
    object_id: object = None
    before: Any = None
    after: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@contextmanager
def audited(
    *,
    action: str,
    actor: Actor,
    object_type: str = "",
    object_id: object = None,
    before: Any = None,
    using: str = DEFAULT_DB_ALIAS,
) -> Iterator[AuditScope]:
    """Run a change and its audit event atomically: if either fails, neither is stored."""
    with transaction.atomic(using=using):
        scope = AuditScope(action, actor, object_type, object_id, before)
        yield scope
        record(
            action=scope.action,
            actor=scope.actor,
            object_type=scope.object_type,
            object_id=scope.object_id,
            before=scope.before,
            after=scope.after,
            metadata=scope.metadata,
            using=using,
        )
