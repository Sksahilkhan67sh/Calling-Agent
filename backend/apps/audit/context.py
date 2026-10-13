"""Per-request facts the audit trail records: client address and user agent.

Bound by middleware once the trusted-proxy client-IP resolver exists (P2-10); empty for CLI and tasks.
The request id comes from the Phase 1 log context.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestInfo:
    source_ip: str | None = None
    user_agent: str = ""


_NO_REQUEST = RequestInfo()
_request_info: contextvars.ContextVar[RequestInfo | None] = contextvars.ContextVar(
    "audit_request_info", default=None
)


def get_request_info() -> RequestInfo:
    return _request_info.get() or _NO_REQUEST


@contextmanager
def request_info(source_ip: str | None, user_agent: str = "") -> Iterator[None]:
    token = _request_info.set(RequestInfo(source_ip=source_ip, user_agent=user_agent))
    try:
        yield
    finally:
        _request_info.reset(token)
