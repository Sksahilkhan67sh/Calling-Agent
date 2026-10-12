from __future__ import annotations

import logging
from typing import Any

from celery import Task, shared_task

from .logging import context

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="apps.core.tasks.heartbeat")
def heartbeat(self: Task[Any, Any], log_context: dict[str, str] | None = None) -> str:
    """Proves Celery wiring. Convention for later tasks: accept ``log_context`` (the
    caller's ``get_context()``) and run the body inside ``context(**log_context)``."""
    with context(**(log_context or {})):
        logger.info("heartbeat", extra={"task_id": self.request.id})
    return "ok"
