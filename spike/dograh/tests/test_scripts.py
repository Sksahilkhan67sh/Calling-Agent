import json
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import pytest
import v01_webhook_auth as v01
import v03_retry_matrix as v03
import v05_list_runs_filter as v05
import v06_status_matrix as v06
import v09_reconnect_seed as v09
import v11_agents_sync as v11
import v12_concurrency as v12
import v14_posture_check as v14


def cap(seq, t, headers, body):
    return {"seq": seq, "received_at": f"2026-01-01T00:00:{t:02d}+00:00", "headers": headers, "body": json.dumps(body)}


def test_v01_flags_signing_headers_only_when_present():
    plain = [cap(1, 0, {"X-Hook": "*** (len=43 chars=base64url)", "User-Agent": "x"}, {})]
    assert v01.analyze(plain)["signing_like"] == []
    assert v01.analyze(plain)["auth_like"] == ["X-Hook"]
    signed = [cap(1, 0, {"X-Signature": "abc"}, {})]
    assert v01.analyze(signed)["signing_like"] == ["X-Signature"]


def test_v03_counts_attempts_and_intervals():
    b = {"run_id": "7"}
    m = v03.matrix([cap(1, 0, {"A": "1", "Date": "x"}, b), cap(2, 10, {"A": "1", "Date": "y"}, b)])
    assert m["7"] == {"attempts": 2, "intervals_s": [10.0], "headers_identical": True, "body_identical": True}


class FakeClient:
    def __init__(self, pages):
        self.pages, self.calls = pages, 0

    def list_runs(self, wf, page, limit, sort_order):
        self.calls += 1

        class R:
            body = {"runs": self.pages[page - 1] if page <= len(self.pages) else []}
        return R


def run(i, ts, attempt=None):
    return {"id": i, "created_at": ts, "initial_context": {"attempt_id": attempt} if attempt else {}}


def test_v05_client_side_scan_finds_and_stops_early():
    pages = [[run(3, "2026-01-03"), run(2, "2026-01-02", "A")], [run(1, "2025-12-01")]]
    hit, n = v05.scan_window(FakeClient(pages), 1, "A", "2026-01-01")
    assert hit["id"] == 2 and n == 1
    hit, n = v05.scan_window(FakeClient(pages), 1, "ZZZ", "2026-01-01")
    assert hit is None and n == 2  # page 2 holds a run older than the window -> stop there


def test_v06_table_groups_status_pairs():
    caps = [cap(1, 0, {}, {"call_status": "user_hangup", "call_disposition": "user_hangup", "recording_url": "u"}),
            cap(2, 1, {}, {"call_status": "no-answer", "call_disposition": "no-answer", "recording_url": ""})]
    assert len(v06.table(caps)) == 2


def test_v09_seed_is_flat_and_size_checked():
    ctx = v09.build_seed_context("a2", "c", "ref", "a1", "we discussed pricing", ["pricing"])
    assert all(isinstance(v, str) for v in ctx.values()) and ctx["previous_attempt_id"] == "a1"
    with pytest.raises(ValueError):
        v09.build_seed_context("a2", "c", "ref", "a1", "x" * 9000)


def test_v11_definition_is_valid_graph_with_fixed_consent_and_webhook():
    d = v11.build_definition({"company": "Acme", "script_prompt": "ask"}, "https://h/x", "cred-1")
    ids = {n["id"] for n in d["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in d["edges"])
    assert sum(n["type"] == "startCall" for n in d["nodes"]) == 1
    assert "may be recorded" in next(n for n in d["nodes"] if n["type"] == "startCall")["data"]["prompt"]
    hook = next(n for n in d["nodes"] if n["type"] == "webhook")["data"]
    assert hook["credential_uuid"] == "cred-1" and "{{initial_context.attempt_id}}" in hook["payload_template"]["attempt_id"]
    assert all(n["data"].get("prompt") for n in d["nodes"] if n["type"] not in ("webhook", "trigger", "qa"))


def test_v12_effective_concurrency_min_and_headroom():
    assert v12.effective_concurrency(30, 10, 50) == 9
    assert v12.effective_concurrency(30, None, 50) == 27
    assert v12.effective_concurrency(1, 10, 50) == 1


def test_v14_flags_defaults_and_never_leaks_values():
    rows = v14.check(v14.parse("OSS_JWT_SECRET=changeme\nENABLE_SIGNUP=false\nLOG_LEVEL=INFO\n"))
    status = {k: s for k, s, _ in rows}
    assert status["OSS_JWT_SECRET"] == "FAIL" and status["ENABLE_SIGNUP"] == "PASS" and status["LOG_LEVEL"] == "PASS"
    assert "changeme" not in str(rows)
