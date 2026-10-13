import re
from pathlib import Path

import pytest

from apps.core.settings_utils import READ_VARIABLES, ConfigError
from tests.conftest import load_settings, make_prod_env

PROD_REQUIRED = [
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "PRIMARY_DB_URL",
    "PRIMARY_DB_POOL_SIZE",
    "CACHE_REDIS_URL",
    "CALL_QUEUE_BROKER_URL",
    "JWT_SIGNING_KEY",
    "FIELD_ENCRYPTION_KEYS",
    "PHONE_HMAC_KEY",
    "DOGRAH_EFFECTIVE_CONCURRENCY",
    "API_RATE_LIMIT_PER_MINUTE",
    "WEBHOOK_RATE_LIMIT_PER_MINUTE",
    "LOGIN_RATE_LIMIT_PER_MINUTE",
    "AXES_FAILURE_LIMIT",
    "TRUSTED_PROXY_COUNT",
    "CORS_ALLOWED_ORIGINS",
    "CSRF_TRUSTED_ORIGINS",
]
DOC = Path(__file__).resolve().parents[3] / "docs" / "phase-1" / "ENV-VARIABLES.md"


@pytest.mark.parametrize("module", ["config.settings.prod", "config.settings.staging"])
def test_production_posture(module, prod_env, monkeypatch):
    s = load_settings(module, prod_env, monkeypatch)
    assert s.DEBUG is False and s.ENABLE_API_DOCS is False
    assert s.ALLOWED_HOSTS == ["api.calls.test"]
    assert s.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert s.SECURE_SSL_REDIRECT is True and s.SECURE_HSTS_SECONDS == 31536000
    assert s.SECURE_HSTS_INCLUDE_SUBDOMAINS and s.SECURE_HSTS_PRELOAD
    assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE and s.SECURE_CONTENT_TYPE_NOSNIFF
    assert s.X_FRAME_OPTIONS == "DENY" and s.SECURE_REFERRER_POLICY == "same-origin"
    assert "Argon2" in s.PASSWORD_HASHERS[0]
    assert s.CORS_ALLOWED_ORIGINS == ["https://dashboard.calls.test"] and s.CORS_ALLOW_ALL_ORIGINS is False
    assert s.DATABASES["default"]["ATOMIC_REQUESTS"] is False
    assert s.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == ["apps.core.permissions.DefaultDeny"]
    assert s.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "apps.accounts.authentication.CookieJWTAuthentication"
    ]
    assert s.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["api-user"] == "600/min"
    assert s.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["webhook"] == "1200/min"
    assert s.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == ["rest_framework.renderers.JSONRenderer"]
    assert s.AUTH_USER_MODEL == "accounts.User" and s.USE_TZ and s.TIME_ZONE == "UTC"
    assert "healthz" in s.SECURE_REDIRECT_EXEMPT[0]
    assert "django.contrib.admin" not in s.INSTALLED_APPS


def test_prod_ignores_debug_environment_variable(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", {**prod_env, "DEBUG": "true", "DJANGO_DEBUG": "1"}, monkeypatch)
    assert s.DEBUG is False


def test_dev_posture(monkeypatch):
    s = load_settings(
        "config.settings.dev", make_prod_env(DJANGO_SECRET_KEY="change-me-dev-only"), monkeypatch
    )
    assert s.DEBUG is True and s.ENABLE_API_DOCS is True
    assert s.CACHES["default"]["BACKEND"].endswith("LocMemCache")


@pytest.mark.parametrize("name", PROD_REQUIRED)
def test_prod_fails_fast_naming_variable_only(name, prod_env, monkeypatch):
    env = {k: v for k, v in prod_env.items() if k != name}
    with pytest.raises(ConfigError) as exc:
        load_settings("config.settings.prod", env, monkeypatch)
    assert name in str(exc.value)
    for value in prod_env.values():
        assert value not in str(exc.value)


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"DJANGO_SECRET_KEY": "short"}, "50 characters"),
        ({"DJANGO_SECRET_KEY": "django-insecure-" + "x" * 60}, "placeholder"),
        ({"DJANGO_SECRET_KEY": "change-me-" + "x" * 60}, "placeholder"),
        ({"DJANGO_ALLOWED_HOSTS": "*"}, "wildcards"),
        ({"PRIMARY_DB_URL": "postgres://u:pw@db/app"}, "sslmode"),
        ({"PRIMARY_DB_URL": "mysql://u:pw@db/app?sslmode=require"}, "scheme"),
        ({"API_RATE_LIMIT_PER_MINUTE": "0"}, "at least"),
        ({"DOGRAH_EFFECTIVE_CONCURRENCY": "ten"}, "integer"),
        ({"FIELD_ENCRYPTION_KEYS": "k1:AAAA"}, "32 bytes"),
        ({"PHONE_HMAC_KEY": "AAAA"}, "at least"),
        ({"JWT_SIGNING_KEY": "j" * 49}, "50 characters"),
    ],
)
def test_prod_rejects_unsafe_values(override, needle, prod_env, monkeypatch):
    with pytest.raises(ConfigError, match=needle):
        load_settings("config.settings.prod", {**prod_env, **override}, monkeypatch)


def test_jwt_key_must_differ_from_secret_key(prod_env, monkeypatch):
    shared = prod_env["DJANGO_SECRET_KEY"]
    with pytest.raises(ConfigError, match="JWT_SIGNING_KEY must differ"):
        load_settings("config.settings.prod", {**prod_env, "JWT_SIGNING_KEY": shared}, monkeypatch)


def test_database_url_parsing_and_pool(prod_env, monkeypatch):
    env = {**prod_env, "PRIMARY_DB_URL": "postgresql://us%40er:p%3Aw@db.x:6543/app?sslmode=verify-full"}
    db = load_settings("config.settings.prod", env, monkeypatch).DATABASES["default"]
    assert (db["USER"], db["PASSWORD"], db["HOST"], db["PORT"], db["NAME"]) == (
        "us@er",
        "p:w",
        "db.x",
        "6543",
        "app",
    )
    assert db["OPTIONS"]["pool"]["max_size"] == 20 and db["CONN_MAX_AGE"] == 0
    with pytest.raises(ConfigError, match="unsupported query option"):
        load_settings(
            "config.settings.prod",
            {**prod_env, "PRIMARY_DB_URL": "postgres://u:p@h/d?sslmode=require&x=1"},
            monkeypatch,
        )
    with pytest.raises(ConfigError, match="host and a database"):
        load_settings(
            "config.settings.prod",
            {**prod_env, "PRIMARY_DB_URL": "postgres://u:p@h/?sslmode=require"},
            monkeypatch,
        )


def test_celery_posture(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", prod_env, monkeypatch)
    assert s.CELERY_ACCEPT_CONTENT == ["json"] and s.CELERY_TASK_SERIALIZER == "json"
    assert s.CELERY_TASK_ACKS_LATE and s.CELERY_TASK_REJECT_ON_WORKER_LOST
    assert s.CELERY_WORKER_PREFETCH_MULTIPLIER == 1 and s.CELERY_TASK_IGNORE_RESULT
    assert {q.name for q in s.CELERY_TASK_QUEUES} == {"default", "dial", "webhooks", "recovery", "analysis"}
    assert list(s.CELERY_BEAT_SCHEDULE) == ["core-heartbeat"]
    assert s.CELERY_TASK_SOFT_TIME_LIMIT < s.CELERY_TASK_TIME_LIMIT


def test_logging_filter_on_every_handler_and_webhook_header_configured(prod_env, monkeypatch):
    s = load_settings(
        "config.settings.prod", {**prod_env, "DOGRAH_WEBHOOK_HEADER_NAME": "X-Hook-Name"}, monkeypatch
    )
    assert all("redact" in h["filters"] for h in s.LOGGING["handlers"].values())
    assert s.LOGGING["filters"]["redact"]["extra_sensitive_keys"] == ["X-Hook-Name"]


def _documented_settings_variables() -> set[str]:
    text = DOC.read_text()
    section = text.split("## Settings variables", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `([A-Z0-9_]+)` \|", section, re.M))


def test_env_variables_doc_matches_settings(prod_env, monkeypatch):
    READ_VARIABLES.clear()
    for module in ("config.settings.prod", "config.settings.dev", "config.settings.test"):
        load_settings(module, prod_env, monkeypatch)
    read = set(READ_VARIABLES)
    documented = _documented_settings_variables()
    assert read - documented == set(), f"undocumented variables: {sorted(read - documented)}"
    assert documented - read == set(), f"documented but never read: {sorted(documented - read)}"
