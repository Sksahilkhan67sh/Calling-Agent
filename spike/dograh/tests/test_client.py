import httpx
import pytest
import call_guard
from dograh_client import DograhClient


def client(handler):
    return DograhClient("https://dograh.test", "k" * 8, transport=httpx.MockTransport(handler))


def test_start_call_blocked_by_guard_makes_no_http_request(monkeypatch):
    monkeypatch.setenv("LIVE_TESTING", "no")
    calls = []
    c = client(lambda req: calls.append(req) or httpx.Response(200, json={}))
    with pytest.raises(call_guard.CallRefused):
        c.start_call("uuid", "+919876543210", {}, "t")
    assert calls == []


def test_start_call_sends_api_key_and_body_once(monkeypatch, tmp_path):
    monkeypatch.setattr(call_guard, "LEDGER", tmp_path / "l.md")
    monkeypatch.setattr(call_guard, "authorize", lambda *a, **k: None)
    seen = []
    c = client(lambda req: seen.append(req) or httpx.Response(200, json={"workflow_run_id": 7}))
    r = c.start_call("uuid", "+919876543210", {"attempt_id": "a1"}, "t")
    assert r.status == 200 and r.body["workflow_run_id"] == 7
    assert len(seen) == 1 and seen[0].headers["x-api-key"] == "k" * 8
    assert seen[0].url.path == "/api/v1/public/agent/workflow/uuid"


def test_timeout_is_reported_not_retried(monkeypatch):
    monkeypatch.setattr(call_guard, "authorize", lambda *a, **k: None)
    n = []

    def boom(req):
        n.append(1)
        raise httpx.ReadTimeout("slow")

    r = client(boom).start_call("u", "+919876543210", {}, "t")
    assert r.status == 0 and r.error == "ReadTimeout" and len(n) == 1


def test_list_runs_encodes_filters():
    seen = []
    c = client(lambda req: seen.append(req) or httpx.Response(200, json={"runs": []}))
    c.list_runs(3, filters=[{"attribute": "campaignId", "type": "number", "value": {"value": 7}}])
    assert "filters=" in str(seen[0].url) and seen[0].url.path == "/api/v1/workflow/3/runs"
