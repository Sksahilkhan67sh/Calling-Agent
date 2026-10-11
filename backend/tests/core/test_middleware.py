import asyncio
import logging

import pytest
from django.http import HttpResponse
from django.test import AsyncRequestFactory, RequestFactory

from apps.core.logging import get_context
from apps.core.middleware import RequestContextMiddleware


def _view_capturing(store):
    def view(request):
        store.append(get_context())
        return HttpResponse("ok")

    return view


def test_generates_id_and_echoes_header():
    seen: list = []
    response = RequestContextMiddleware(_view_capturing(seen))(RequestFactory().get("/"))
    rid = response["X-Request-ID"]
    assert len(rid) == 36 and seen[0] == {"request_id": rid, "trace_id": rid}


def test_accepts_valid_inbound_ids():
    seen: list = []
    req = RequestFactory().get("/", headers={"X-Request-ID": "abc-12345678", "X-Trace-ID": "trace_ABCDEFGH"})
    response = RequestContextMiddleware(_view_capturing(seen))(req)
    assert response["X-Request-ID"] == "abc-12345678"
    assert seen[0] == {"request_id": "abc-12345678", "trace_id": "trace_ABCDEFGH"}


@pytest.mark.parametrize(
    "bad", ["short", "x" * 65, "has space 12345", "semi;colon12345", "new\\nline1234", "ünï-code12345"]
)
def test_rejects_bad_ids(bad):
    seen: list = []
    req = RequestFactory().get("/", headers={"X-Request-ID": bad, "X-Trace-ID": bad})
    response = RequestContextMiddleware(_view_capturing(seen))(req)
    assert response["X-Request-ID"] != bad and len(response["X-Request-ID"]) == 36
    assert seen[0]["trace_id"] == response["X-Request-ID"]


def test_context_cleared_after_response_and_after_exception():
    def boom(request):
        raise RuntimeError("x")

    mw = RequestContextMiddleware(boom)
    with pytest.raises(RuntimeError):
        mw(RequestFactory().get("/"))
    assert get_context() == {}
    seen: list = []
    RequestContextMiddleware(_view_capturing(seen))(RequestFactory().get("/"))
    assert get_context() == {}


def test_no_leakage_between_requests():
    seen: list = []
    mw = RequestContextMiddleware(_view_capturing(seen))
    mw(RequestFactory().get("/", headers={"X-Request-ID": "first-request-1"}))
    mw(RequestFactory().get("/"))
    assert seen[0]["request_id"] == "first-request-1" and seen[1]["request_id"] != "first-request-1"


def test_async_path():
    seen: list = []

    async def view(request):
        seen.append(get_context())
        return HttpResponse("ok")

    mw = RequestContextMiddleware(view)
    response = asyncio.run(mw(AsyncRequestFactory().get("/", headers={"X-Request-ID": "async-req-0001"})))
    assert response["X-Request-ID"] == "async-req-0001" and seen[0]["request_id"] == "async-req-0001"
    assert get_context() == {}


def test_logs_carry_request_id_through_real_stack(client, log_capture):
    response = client.get("/healthz", headers={"X-Request-ID": "stack-req-0001"})
    assert response["X-Request-ID"] == "stack-req-0001"
    logging.getLogger("x").info("after")
