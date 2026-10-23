import os

for k, v in {
    "DJANGO_SECRET_KEY": "test-only-secret-key-test-only-secret-key-test-only-secret-key",
    "JWT_SIGNING_KEY": "test-only-jwt-signing-key-0123456789abcdef0123456789",
    "DJANGO_ALLOWED_HOSTS": "testserver,localhost",
    "PRIMARY_DB_URL": "postgres://calling:calling@localhost:5432/calling",
    "PRIMARY_DB_POOL_SIZE": "5",
    "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    "CALL_QUEUE_BROKER_URL": "redis://localhost:6379/0",
    "API_RATE_LIMIT_PER_MINUTE": "1000",
    "AXES_FAILURE_LIMIT": "3",
    "FIELD_ENCRYPTION_KEYS": "egsE0xEKI-D7TSQjfs-ner_qJpnp-bjBFoj4th8G9ek=",
    "PHONE_HMAC_KEY": "test-only-phone-hmac-key",
    "DOGRAH_BASE_URL": "https://dograh.test",
    "DOGRAH_API_KEY": "test-only-dograh-key",
    "DOGRAH_REQUEST_TIMEOUT_SECONDS": "5",
    "DOGRAH_ALLOWED_ARTIFACT_HOSTS": "artifacts.dograh.test",
    "DOGRAH_MAX_ARTIFACT_BYTES": "1024",
    "DOGRAH_ARTIFACT_DEADLINE_SECONDS": "5",
    "DOGRAH_RUN_PATH": "/api/v1/runs",
    "DOGRAH_WORKFLOW_PATH": "/api/v1/agents",
    "PUBLIC_BASE_URL": "https://api.example.test",
    "DOGRAH_WEBHOOK_SECRET": "test-webhook-secret-test-webhook-secret",
    "DOGRAH_EFFECTIVE_CONCURRENCY": "2",
    "DOGRAH_COMPLETED_DISPOSITIONS": "goal_met,completed",
    "RECONCILE_CEILING_SECONDS": "900",
    "WEBHOOK_RATE_LIMIT_PER_MINUTE": "1000",
}.items():
    os.environ.setdefault(k, v)

from .base import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
