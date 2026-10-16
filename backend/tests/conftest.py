import base64
import logging
import secrets
import sys
import uuid

import pytest
import redis as redis_lib
from django.conf import settings

from apps.core.logging import clear_context


def make_prod_env(**overrides: str) -> dict[str, str]:
    """A valid production environment with throwaway random values (never stored)."""
    env = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ALLOWED_HOSTS": "api.calls.test",
        "PRIMARY_DB_URL": f"postgres://app:{secrets.token_hex(12)}@db.internal:5432/app?sslmode=require",
        "PRIMARY_DB_POOL_SIZE": "20",
        "CACHE_REDIS_URL": f"redis://:{secrets.token_hex(12)}@cache.internal:6379/1",
        "CALL_QUEUE_BROKER_URL": f"redis://:{secrets.token_hex(12)}@cache.internal:6379/0",
        "JWT_SIGNING_KEY": secrets.token_urlsafe(48),
        "FIELD_ENCRYPTION_KEYS": "k2026a:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "PHONE_HMAC_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "DOGRAH_EFFECTIVE_CONCURRENCY": "20",
        "API_RATE_LIMIT_PER_MINUTE": "600",
        "WEBHOOK_RATE_LIMIT_PER_MINUTE": "1200",
        "LOGIN_RATE_LIMIT_PER_MINUTE": "5",
        "SESSION_ABSOLUTE_MAX_DAYS": "7",
        "AXES_FAILURE_LIMIT": "5",
        "TRUSTED_PROXY_COUNT": "1",
        "CORS_ALLOWED_ORIGINS": "https://dashboard.calls.test",
        "CSRF_TRUSTED_ORIGINS": "https://dashboard.calls.test",
    }
    env.update(overrides)
    return env


def load_settings(module: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch):
    """Import a settings module fresh under exactly ``env``."""
    import importlib
    import os

    for name in list(os.environ):
        if name.isupper() and name not in {"PATH", "HOME", "LANG", "TZ"}:
            monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    for loaded in [m for m in sys.modules if m.startswith("config.settings")]:
        monkeypatch.delitem(sys.modules, loaded)
    return importlib.import_module(module)


@pytest.fixture(autouse=True)
def _clean_log_context():
    clear_context()
    yield
    clear_context()


@pytest.fixture
def frozen_time():
    """Freeze the clock at a fixed UTC instant."""
    from freezegun import freeze_time

    with freeze_time("2026-10-11 12:00:00", tz_offset=0) as frozen:
        yield frozen


@pytest.fixture
def prod_env() -> dict[str, str]:
    return make_prod_env()


@pytest.fixture
def log_capture():
    """Capture formatted JSON lines from the root logger through the real filter and formatter."""
    import io

    from apps.core.logging import JsonFormatter, RedactionFilter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(extra_sensitive_keys=[settings.DOGRAH_WEBHOOK_HEADER_NAME]))
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield stream
    root.removeHandler(handler)
    root.setLevel(previous)


@pytest.fixture
def redis_client():
    """Real Redis, isolated by a per-test key prefix and cleaned afterwards."""
    client = redis_lib.Redis.from_url(settings.CACHE_REDIS_URL, decode_responses=True)
    try:
        client.ping()
    except redis_lib.RedisError:
        pytest.skip("Redis not available")
    prefix = f"test:{uuid.uuid4().hex}:"
    yield client, prefix
    for key in client.scan_iter(f"{prefix}*"):
        client.delete(key)
    client.close()
