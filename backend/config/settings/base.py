"""Settings shared by every environment. All environment access goes through settings_utils."""

from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from kombu import Exchange, Queue

from apps.core.crypto import parse_encryption_keys, parse_hmac_key
from apps.core.logging import build_logging_config
from apps.core.settings_utils import (
    ConfigError,
    as_csv_hosts,
    as_int,
    as_list,
    optional,
    required,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_ALLOWED_DB_OPTIONS = {"sslmode", "sslrootcert", "connect_timeout"}


def database_from_url(url: str, *, variable: str, pool_size: int) -> dict[str, Any]:
    """Parse ``postgres://user:pass@host:port/name?sslmode=require`` into a Django DATABASES entry."""
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise ConfigError(f"{variable} must use the postgres:// or postgresql:// scheme")
    name = parts.path.lstrip("/")
    if not parts.hostname or not name:
        raise ConfigError(f"{variable} must include a host and a database name")
    options: dict[str, Any] = {"connect_timeout": 5}
    for key, value in parse_qsl(parts.query):
        if key not in _ALLOWED_DB_OPTIONS:
            raise ConfigError(f"{variable} contains an unsupported query option")
        options[key] = int(value) if key == "connect_timeout" and value.isdigit() else value
    options["pool"] = {"min_size": min(2, pool_size), "max_size": pool_size, "timeout": 10}
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname,
        "PORT": str(parts.port or 5432),
        "ATOMIC_REQUESTS": False,  # explicit transactions are the rule (dialer, Phase 4)
        "CONN_MAX_AGE": 0,  # connection reuse is handled by the pool
        "OPTIONS": options,
    }


SECRET_KEY = required("DJANGO_SECRET_KEY", secret=True)
DEBUG = False
ALLOWED_HOSTS = as_csv_hosts("DJANGO_ALLOWED_HOSTS")
ENABLE_API_DOCS = False
APP_VERSION = optional("APP_VERSION")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
]
AUTH_USER_MODEL = "accounts.User"
# Only M2M through tables use this; every model declares a UUID primary key.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MIDDLEWARE = [
    "apps.core.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

USE_TZ = True
TIME_ZONE = "UTC"

_POOL_SIZE = as_int("PRIMARY_DB_POOL_SIZE", minimum=1, maximum=200)
DATABASES = {
    "default": database_from_url(
        required("PRIMARY_DB_URL", secret=True), variable="PRIMARY_DB_URL", pool_size=_POOL_SIZE
    )
}

CACHE_REDIS_URL = required("CACHE_REDIS_URL", secret=True)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": CACHE_REDIS_URL}}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- rates (Threat Model risk #6): production requires explicit values (prod.py)
API_RATE_LIMIT_PER_MINUTE = as_int("API_RATE_LIMIT_PER_MINUTE", 1000, minimum=1)
WEBHOOK_RATE_LIMIT_PER_MINUTE = as_int("WEBHOOK_RATE_LIMIT_PER_MINUTE", 1000, minimum=1)
LOGIN_RATE_LIMIT_PER_MINUTE = as_int("LOGIN_RATE_LIMIT_PER_MINUTE", 5, minimum=1)

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.permissions.DefaultDeny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],  # Phase 2 adds authentication
    "DEFAULT_THROTTLE_CLASSES": ["apps.core.throttles.ApiUserThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": f"{LOGIN_RATE_LIMIT_PER_MINUTE}/min",
        "api-user": f"{API_RATE_LIMIT_PER_MINUTE}/min",
        "api-client": f"{API_RATE_LIMIT_PER_MINUTE}/min",
        "webhook": f"{WEBHOOK_RATE_LIMIT_PER_MINUTE}/min",
    },
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.safe_exception_handler",
    "UNAUTHENTICATED_USER": None,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "AI Calling Agent API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["apps.core.permissions.PublicEndpoint"],  # docs are mounted in dev only
    "SERVE_AUTHENTICATION": [],
}

CORS_ALLOWED_ORIGINS = as_list("CORS_ALLOWED_ORIGINS", [])
CORS_ALLOW_ALL_ORIGINS = False

# ---- secrets for later phases, validated now so a bad key never reaches production
FIELD_ENCRYPTION_KEYS = parse_encryption_keys(required("FIELD_ENCRYPTION_KEYS", secret=True))
PHONE_HMAC_KEY = parse_hmac_key(required("PHONE_HMAC_KEY", secret=True))
JWT_SIGNING_KEY = required("JWT_SIGNING_KEY", secret=True)
DOGRAH_EFFECTIVE_CONCURRENCY = as_int("DOGRAH_EFFECTIVE_CONCURRENCY", minimum=1)  # used from Phase 4
DOGRAH_WEBHOOK_HEADER_NAME = optional("DOGRAH_WEBHOOK_HEADER_NAME", "X-Dograh-Webhook-Secret")

# ---- logging
LOG_LEVEL = optional("LOG_LEVEL", "INFO").upper()
LOGGING = build_logging_config(level=LOG_LEVEL, extra_sensitive_keys=(DOGRAH_WEBHOOK_HEADER_NAME,))

# ---- Celery (namespace CELERY). The durable retry schedule lives in PostgreSQL
# (call_attempt.next_dispatch_at); the broker is an optimisation (Backend Design §6).
CELERY_BROKER_URL = required("CALL_QUEUE_BROKER_URL", secret=True)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # keep our JSON logging and redaction
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = tuple(
    Queue(name, Exchange(name), routing_key=name)
    for name in ("default", "dial", "webhooks", "recovery", "analysis")
)
CELERY_TASK_ROUTES = {"apps.core.tasks.heartbeat": {"queue": "default"}}
CELERY_BEAT_SCHEDULE = {
    "core-heartbeat": {"task": "apps.core.tasks.heartbeat", "schedule": 60.0},
}
