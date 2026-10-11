"""Real worker + beat against real Redis. Observed through the processes' JSON logs."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[1]


def _env(queue_db: int) -> dict[str, str]:
    from django.conf import settings

    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "tests.fast_beat_settings"
    env["CALL_QUEUE_BROKER_URL"] = settings.CELERY_BROKER_URL.rsplit("/", 1)[0] + f"/{queue_db}"
    return env


def _start(args: list[str], env: dict[str, str], log: Path) -> subprocess.Popen:
    handle = log.open("w")
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "celery", "-A", "config", *args],
        cwd=BACKEND,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


def _wait_for(log: Path, needle: str, timeout: float = 30.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = log.read_text()
        if needle in text:
            return text
        time.sleep(0.25)
    raise AssertionError(f"{needle!r} not seen in worker log:\n{log.read_text()[-2000:]}")


def _stop(*procs: subprocess.Popen) -> None:
    for proc in procs:
        proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_worker_consumes_heartbeat_and_beat_schedules_it(tmp_path):
    import redis as redis_lib

    env = _env(queue_db=14)
    redis_lib.Redis.from_url(env["CALL_QUEUE_BROKER_URL"]).flushdb()
    worker_log, beat_log = tmp_path / "worker.log", tmp_path / "beat.log"
    worker = _start(["worker", "--pool=solo", "-Q", "default", "--loglevel=INFO"], env, worker_log)
    beat = _start(["beat", "--schedule", str(tmp_path / "beat-schedule"), "--loglevel=INFO"], env, beat_log)
    try:
        _wait_for(beat_log, "Sending due task core-heartbeat")
        seen = _wait_for(worker_log, '"message": "heartbeat"')
        lines = [json.loads(x) for x in seen.splitlines() if x.startswith("{") and '"heartbeat"' in x]
        assert lines and lines[0]["task_id"] and lines[0]["logger"] == "apps.core.tasks"

        # A directly sent task carries the caller's log context across the broker.
        from apps.core.tasks import heartbeat

        marker = f"req-{uuid.uuid4().hex[:12]}"
        from kombu import Connection

        with Connection(env["CALL_QUEUE_BROKER_URL"]) as connection:
            heartbeat.apply_async(kwargs={"log_context": {"request_id": marker}}, connection=connection)
        text = _wait_for(worker_log, marker)
        assert any(
            json.loads(x).get("request_id") == marker
            for x in text.splitlines()
            if x.startswith("{") and marker in x
        )
    finally:
        _stop(worker, beat)
