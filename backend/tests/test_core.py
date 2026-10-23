import io
import logging

from django.conf import settings

from apps.core.logging import RedactingJsonFormatter
from config import celery_app


def test_logs_never_contain_secrets_phones_or_recording_urls():
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(RedactingJsonFormatter())
    log = logging.getLogger("redaction-test")
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.info("Authorization: Bearer abc.def.ghi Cookie: sessionid=s3cr3t X-API-Key: key-123")
    log.info("dial +91 98765 43210 and 9876543210 via https://x.s3.amazonaws.com/recordings/a.wav?X-Amz-Signature=zzz")
    log.info("hook", extra={"password": "hunter2", "token": "tok-999", "call_id": "c-1"})
    try:
        raise ValueError("bad url https://h/rec?token=leak123")
    except ValueError:
        log.exception("failed")
    out = buf.getvalue()
    for leaked in ("abc.def.ghi", "s3cr3t", "key-123", "98765", "9876543210", "recordings/a.wav", "zzz", "hunter2", "tok-999", "leak123"):
        assert leaked not in out
    assert "c-1" in out


def test_celery_is_crash_safe_and_has_queues():
    c = celery_app.conf
    assert c.task_acks_late and c.task_reject_on_worker_lost
    assert c.task_soft_time_limit < c.task_time_limit
    assert {q.name for q in c.task_queues} == {"default", "dial", "webhook", "recovery", "analysis"}


def test_health_ok(client, db):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_argon2_is_primary_hasher():
    assert settings.MFA_REQUIRED_ROLES >= {"Admin", "Campaign Manager"}
