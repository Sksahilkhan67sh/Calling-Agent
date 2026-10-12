"""Request/trace id middleware (sync and async)."""

import re
import uuid
from collections.abc import Callable
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest

from .logging import context

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"


def _accept_or_generate(value: str | None) -> str:
    """Inbound ids are untrusted: only a conservative charset and length is accepted."""
    if value and _ID_PATTERN.match(value):
        return value
    return str(uuid.uuid4())


class RequestContextMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def _ids(self, request: HttpRequest) -> tuple[str, str]:
        request_id = _accept_or_generate(request.headers.get(REQUEST_ID_HEADER))
        trace_header = request.headers.get(TRACE_ID_HEADER)
        trace_id = trace_header if trace_header and _ID_PATTERN.match(trace_header) else request_id
        return request_id, trace_id

    def __call__(self, request: HttpRequest) -> Any:
        if self._is_async:
            return self._acall(request)
        request_id, trace_id = self._ids(request)
        with context(request_id=request_id, trace_id=trace_id):
            response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response

    async def _acall(self, request: HttpRequest) -> Any:
        request_id, trace_id = self._ids(request)
        with context(request_id=request_id, trace_id=trace_id):
            response = await self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response
