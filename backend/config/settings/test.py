"""Test settings: fake secrets (tests only), fast hasher, no network by default."""

import base64
import os

_FAKE = {
    "DJANGO_SECRET_KEY": "test-only-" + "k" * 60,
    "DJANGO_ALLOWED_HOSTS": "testserver,localhost",
    "PRIMARY_DB_URL": "postgres://agent:agent-dev-only@127.0.0.1:5432/agent_test",
    "PRIMARY_DB_POOL_SIZE": "2",
    "CACHE_REDIS_URL": "redis://127.0.0.1:6379/1",
    "CALL_QUEUE_BROKER_URL": "redis://127.0.0.1:6379/0",
    "JWT_SIGNING_KEY": "test-only-jwt-" + "j" * 40,
    "FIELD_ENCRYPTION_KEYS": "t1:" + base64.b64encode(b"t" * 32).decode(),
    "PHONE_HMAC_KEY": base64.b64encode(b"h" * 32).decode(),
    "DOGRAH_EFFECTIVE_CONCURRENCY": "5",
}
for _name, _value in _FAKE.items():
    os.environ.setdefault(_name, _value)

from .base import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; never outside tests
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
DATABASES["default"]["OPTIONS"].pop("pool", None)  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = False

# Test-only app with a scoped model and views (never installed by dev/staging/prod).
INSTALLED_APPS = [*INSTALLED_APPS, "tests.testapp"]  # noqa: F405
