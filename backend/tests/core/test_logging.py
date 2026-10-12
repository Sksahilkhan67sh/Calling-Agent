import asyncio
import json
import logging
import threading
import time

import pytest

from apps.core import logging as lg

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
PAT = "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwx"


@pytest.mark.parametrize(
    ("text", "forbidden"),
    [
        ("Authorization: Bearer abcdef1234567890", "abcdef1234567890"),
        ("header Bearer abcdef1234567890 sent", "abcdef1234567890"),
        (f"token {JWT}", JWT),
        (f"pushed with {PAT}", PAT),
        ("key sk-abcdefghijklmnopqrstuvwxyz123456", "sk-abcdef"),
        ("aws AKIAABCDEFGHIJKLMNOP", "AKIAABCDEF"),
        ("password=hunter2hunter2", "hunter2"),
        ('{"api_key": "abc123secretvalue"}', "abc123secretvalue"),
        ("X-Api-Key: zzzzSECRETzzzz", "zzzzSECRETzzzz"),
        ("Cookie: sessionid=abcdefabcdef; csrftoken=qwerty", "abcdefabcdef"),
        ("GET /cb?token=SECRETTOKEN&ok=1", "SECRETTOKEN"),
        ("https://s3.example.com/b/o?X-Amz-Signature=deadbeef&X-Amz-Credential=AKIA1&Expires=99", "deadbeef"),
        ("redis://:supersecretpw@cache:6379/0", "supersecretpw"),
        ("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----", "MIIEvQ"),
        ("https://api.dograh.example/files/recordings/run-91/audio.wav", "run-91"),
        ("https://storage.example.com/transcripts/abc.json?x=1", "abc.json"),
    ],
)
def test_redacts_secrets(text, forbidden):
    out = lg.redact_text(text)
    assert forbidden not in out
    assert lg.redact_text(out) == out  # idempotent


def test_url_keeps_host_and_path_but_not_token():
    out = lg.redact_text("GET https://api.example.com/v1/runs?token=abc&page=2")
    assert "https://api.example.com/v1/runs?token=[REDACTED]&page=2" in out


@pytest.mark.parametrize(
    "text",
    [
        "campaign started for 12 contacts",
        "2026-10-11T12:25:30.123Z call completed",
        "id 5f0c1e2a-9b1d-4c3e-8a7f-1234567890ab ok",
        "elapsed 1234 ms, retries 2",
        "user accessed_at updated",
        "version 5.2.17 running",
    ],
)
def test_ordinary_text_unchanged(text):
    assert lg.redact_text(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("call +919876543210 now", "call +91***10 now"),
        ("call +14155550100", "call +1***00"),
        ("call +447911123456", "call +44***56"),
        ("call +971501234567", "call +971***67"),
        ("dial 98765 43210", "dial ***10"),
        ("dial (415) 555-0100", "dial ***00"),
        ("dial 415-555-0100.", "dial ***00."),
    ],
)
def test_phone_masking(text, expected):
    assert lg.redact_text(text) == expected


def test_phone_masking_in_exception_text_and_extras(log_capture):
    log = logging.getLogger("t")
    try:
        raise RuntimeError("failed for +919876543210 with password=pw12345678")
    except RuntimeError:
        log.exception("boom", extra={"contact": {"phone": "+919876543210", "note": "ok"}})
    line = json.loads(log_capture.getvalue().strip().splitlines()[-1])
    blob = json.dumps(line)
    assert "9876543210" not in blob and "pw12345678" not in blob
    assert line["contact"]["note"] == "ok"
    assert "Traceback" in line["exception"]


def test_structured_key_redaction_nested():
    value = {
        "Authorization": "Bearer x",
        "headers": {"X-Api-Key": "k", "Set-Cookie": "c"},
        "list": [{"password": "p"}, "token=abc12345"],
        "refresh": "r",
        "access": "a",
        "accessed_at": "today",
        "webhook": {"x-dograh-webhook-secret": "s"},
    }
    out = lg.redact_value(value)
    assert out["Authorization"] == "[REDACTED]" and out["refresh"] == "[REDACTED]"
    assert out["headers"] == {"X-Api-Key": "[REDACTED]", "Set-Cookie": "[REDACTED]"}
    assert out["list"][0]["password"] == "[REDACTED]" and "abc12345" not in out["list"][1]
    assert out["accessed_at"] == "today"
    assert out["webhook"]["x-dograh-webhook-secret"] == "[REDACTED]"


def test_configured_header_name_is_sensitive():
    extra = frozenset({"x_custom_hook"})
    assert lg.redact_value({"X-Custom-Hook": "v"}, extra_keys=extra) == {"X-Custom-Hook": "[REDACTED]"}
    assert "v-secret-1" not in lg.redact_text("X-Custom-Hook: v-secret-1", extra_keys=extra)


class _Odd:
    def __str__(self):
        raise RuntimeError("nope")


def test_odd_inputs_do_not_crash():
    assert lg.redact_value(b"token=abcdef123 \xff") == "token=[REDACTED] \ufffd"
    assert lg.redact_value(_Odd()) == "[UNREPRESENTABLE]"
    assert lg.redact_value(None) is None and lg.redact_value(3) == 3 and lg.redact_value(True) is True
    assert lg.redact_value({1: "x"}) == {"1": "x"}
    deep: object = "leaf"
    for _ in range(20):
        deep = {"n": deep}
    assert "[TRUNCATED]" in json.dumps(lg.redact_value(deep))
    assert lg.redact_text("") == ""


def test_regex_performance_no_catastrophic_backtracking():
    hostile = [
        "a" * 200_000,
        "password" * 20_000,
        "1 " * 100_000,
        "token=" + "x" * 200_000,
        "+" + "1-" * 100_000,
        "https://h/" + "a/" * 50_000,
        "-----BEGIN PRIVATE KEY-----" + "A" * 100_000,
        "Bearer " + "a" * 100_000,
        "http://" + "a" * 100_000,
    ]
    for text in hostile:
        start = time.perf_counter()
        lg.redact_text(text)
        assert time.perf_counter() - start < 2.0, text[:30]


def test_filter_handles_bad_format_args():
    record = logging.LogRecord("n", logging.INFO, "f", 1, "value %d", ("not-int",), None)
    assert lg.RedactionFilter().filter(record) is True
    assert "value" in record.msg


def test_context_binding_and_restore(log_capture):
    log = logging.getLogger("ctx")
    with lg.context(request_id="req-12345678", campaign_id="c1"):
        log.info("inside")
        with lg.context(attempt_id="a1"):
            assert lg.get_context() == {"request_id": "req-12345678", "campaign_id": "c1", "attempt_id": "a1"}
        assert "attempt_id" not in lg.get_context()
    log.info("outside")
    first, second = (json.loads(x) for x in log_capture.getvalue().strip().splitlines())
    assert first["request_id"] == "req-12345678" and first["campaign_id"] == "c1"
    assert "request_id" not in second
    assert {"timestamp", "level", "logger", "message"} <= first.keys()
    assert first["timestamp"].endswith("+00:00")


def test_bind_rejects_unknown_and_skips_none_and_truncates():
    with pytest.raises(ValueError):
        lg.bind_context(password="x")
    lg.bind_context(call_id=None, trace_id="t" * 500)
    assert lg.get_context() == {"trace_id": "t" * 128}
    lg.clear_context()
    assert lg.get_context() == {}


def test_context_isolated_between_threads_and_async():
    seen: dict[str, dict] = {}

    def worker():
        seen["thread"] = lg.get_context()

    with lg.context(request_id="main-request-1"):
        t = threading.Thread(target=worker)
        t.start()
        t.join()

        async def one(name):
            with lg.context(call_id=name):
                await asyncio.sleep(0.01)
                return lg.get_context()["call_id"]

        async def run():
            return await asyncio.gather(one("a"), one("b"))

        assert asyncio.run(run()) == ["a", "b"]
    assert seen["thread"] == {}


def test_context_crosses_celery_task_boundary():
    from apps.core.tasks import heartbeat

    with lg.context(request_id="req-abcdefgh"):
        passed = lg.get_context()
    assert heartbeat.apply(kwargs={"log_context": passed}).get() == "ok"


def test_json_formatter_pretty_and_exception():
    fmt = lg.JsonFormatter(indent=2)
    try:
        raise ValueError("x")
    except ValueError:
        import sys

        rec = logging.LogRecord("n", logging.ERROR, "f", 1, "m", (), sys.exc_info())
    assert "\n  " in fmt.format(rec) and "ValueError" in json.loads(fmt.format(rec))["exception"]


def test_every_handler_has_redaction_filter():
    cfg = lg.build_logging_config(extra_sensitive_keys=("X-Hook",))
    assert all("redact" in h["filters"] for h in cfg["handlers"].values())
    assert cfg["filters"]["redact"]["extra_sensitive_keys"] == ["X-Hook"]


def test_log_capture_secrets_and_recording_urls_never_appear(log_capture):
    """Django-Backend-Design §8 'Secrets': a realistic mix must leave no secret in the output."""
    log = logging.getLogger("apps.webhooks")
    secret = "whsec_" + "a1b2c3d4e5f6" * 4
    recording = "https://dograh.example/api/v1/public/download/recordings/RUNTOKEN123/audio"
    signed = "https://bucket.s3.amazonaws.com/rec/1.wav?X-Amz-Signature=SIGVALUE&X-Amz-Expires=60"
    log.info("webhook X-Dograh-Webhook-Secret: %s received", secret)
    log.warning("artifact %s and %s for +919876543210", recording, signed)
    log.info(
        "headers",
        extra={"headers": {"X-Dograh-Webhook-Secret": secret, "Authorization": "Bearer abcdefgh12345"}},
    )
    out = log_capture.getvalue()
    for forbidden in (secret, "RUNTOKEN123", "SIGVALUE", "9876543210", "abcdefgh12345", "audio"):
        assert forbidden not in out


def test_long_digit_runs_are_not_masked_as_phones():
    assert lg.redact_text("order 1234567890123456") == "order 1234567890123456"


def test_stack_info_and_preformatted_exc_text_redacted():
    record = logging.LogRecord("n", logging.ERROR, "f", 1, "m", (), None)
    record.stack_info = "stack password=hunter2hunter2"
    record.exc_text = "trace token=abcdef123456"
    lg.RedactionFilter().filter(record)
    assert "hunter2" not in record.stack_info and "abcdef123456" not in record.exc_text


def test_log_timestamp_is_utc_and_follows_the_clock(frozen_time, log_capture):
    logging.getLogger("clock").info("tick")
    first = json.loads(log_capture.getvalue().strip().splitlines()[-1])["timestamp"]
    assert first == "2026-10-11T12:00:00.000+00:00"
    frozen_time.tick(60)
    logging.getLogger("clock").info("tock")
    assert json.loads(log_capture.getvalue().strip().splitlines()[-1])["timestamp"].startswith(
        "2026-10-11T12:01:00"
    )
