"""Settings shared by every environment. All environment access goes through settings_utils."""

from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from kombu import Exchange, Queue

from apps.accounts.roles import ALL_ROLES, ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER
from apps.core.crypto import parse_encryption_keys, parse_hmac_key
from apps.core.logging import build_logging_config
from apps.core.settings_utils import (
    ConfigError,
    as_bool,
    as_csv_hosts,
    as_int,
    as_list,
    as_origins,
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
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "full_name")},
    },
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

# ---- browser access: cookie auth needs credentialed CORS, so prod requires an explicit origin list
CORS_ALLOWED_ORIGINS = as_origins("CORS_ALLOWED_ORIGINS", [])
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = as_origins("CSRF_TRUSTED_ORIGINS", [])

# ---- secrets for later phases, validated now so a bad key never reaches production
FIELD_ENCRYPTION_KEYS = parse_encryption_keys(required("FIELD_ENCRYPTION_KEYS", secret=True))
PHONE_HMAC_KEY = parse_hmac_key(required("PHONE_HMAC_KEY", secret=True))
JWT_SIGNING_KEY = required("JWT_SIGNING_KEY", secret=True)
DOGRAH_EFFECTIVE_CONCURRENCY = as_int("DOGRAH_EFFECTIVE_CONCURRENCY", minimum=1)  # used from Phase 4
DOGRAH_WEBHOOK_HEADER_NAME = optional("DOGRAH_WEBHOOK_HEADER_NAME", "X-Dograh-Webhook-Secret")

# ---- authentication (Django-Backend-Design §4.1). Algorithm, issuer, audience and cookie names are
# code, not environment: a deployment must not be able to weaken them.
API_VERSION_PREFIX = "v1"  # Backend/API-Specification.yaml servers[].url ends in /v1
JWT_ALGORITHM = "HS256"  # symmetric: one service signs and verifies, so no key distribution
JWT_ISSUER = "ai-calling-agent"
JWT_AUDIENCE = "ai-calling-agent-dashboard"
JWT_ACCESS_LIFETIME_SECONDS = as_int("JWT_ACCESS_LIFETIME_SECONDS", 900, minimum=60, maximum=3600)
# Refresh tokens rotate on every use, so this is an idle timeout: 24 h idle forces a new login (+MFA).
JWT_REFRESH_LIFETIME_SECONDS = as_int("JWT_REFRESH_LIFETIME_SECONDS", 86400, minimum=3600, maximum=2592000)
SIMPLE_JWT: dict[str, Any] = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=JWT_ACCESS_LIFETIME_SECONDS),
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=JWT_REFRESH_LIFETIME_SECONDS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": JWT_ALGORITHM,
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "ISSUER": JWT_ISSUER,
    "AUDIENCE": JWT_AUDIENCE,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
}

AUTH_COOKIE_SAMESITE = optional("AUTH_COOKIE_SAMESITE", "Lax").capitalize()
if AUTH_COOKIE_SAMESITE not in {"Lax", "Strict"}:
    raise ConfigError("AUTH_COOKIE_SAMESITE must be Lax or Strict")
AUTH_COOKIE_DOMAIN = optional("AUTH_COOKIE_DOMAIN") or None
AUTH_TOKENS_IN_BODY = as_bool("AUTH_TOKENS_IN_BODY", False)  # non-browser clients only
AUTH_REFRESH_COOKIE_PATH = f"/{API_VERSION_PREFIX}/auth/"


def cookie_names(*, secure: bool, domain: str | None) -> tuple[str, str, str]:
    """(access, refresh, csrf) cookie names.

    ``__Host-`` requires Secure, Path=/ and no Domain, so it suits the access and CSRF cookies. The refresh
    cookie is path-scoped, which ``__Host-`` forbids, so it uses ``__Secure-``. Browsers refuse prefixed
    cookies over plain HTTP, hence plain names when not secure (local dev only).
    """
    if not secure:
        return "access", "refresh", "csrftoken"
    wide = "__Secure-" if domain else "__Host-"
    return f"{wide}access", "__Secure-refresh", f"{wide}csrftoken"


AUTH_COOKIE_SECURE = True
AUTH_ACCESS_COOKIE_NAME, AUTH_REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(
    secure=AUTH_COOKIE_SECURE, domain=AUTH_COOKIE_DOMAIN
)
# Double-submit CSRF: the SPA reads the CSRF cookie and echoes it in X-CSRFToken, so it is not HttpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = AUTH_COOKIE_SAMESITE
CSRF_COOKIE_DOMAIN = AUTH_COOKIE_DOMAIN

# ---- brute-force protection (django-axes is wired in P2-10). Production requires explicit values.
AXES_FAILURE_LIMIT = as_int("AXES_FAILURE_LIMIT", 5, minimum=1)
AXES_COOLOFF_MINUTES = as_int("AXES_COOLOFF_MINUTES", 15, minimum=1)
AXES_COOLOFF_TIME = timedelta(minutes=AXES_COOLOFF_MINUTES)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]  # one account from one address, not a global lock
AXES_RESET_ON_SUCCESS = True
# Number of reverse proxies in front of the API. The client address is the entry that many hops from
# the right of X-Forwarded-For; the left-most value is attacker-controlled and never trusted.
TRUSTED_PROXY_COUNT = as_int("TRUSTED_PROXY_COUNT", 0, minimum=0, maximum=10)

# ---- MFA (TOTP, RFC 6238). SHA-1 and 6 digits are what authenticator apps universally support.
MFA_REQUIRED_ROLES = as_list("MFA_REQUIRED_ROLES", [ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER])
if not set(MFA_REQUIRED_ROLES) <= set(ALL_ROLES):
    raise ConfigError("MFA_REQUIRED_ROLES contains an unknown role name")
MFA_ISSUER_NAME = optional("MFA_ISSUER_NAME", "AI Calling Agent")
MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS = as_int(
    "MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS", 600, minimum=60, maximum=1800
)
MFA_TOTP_ALGORITHM = "SHA1"
MFA_TOTP_DIGITS = 6
MFA_TOTP_PERIOD_SECONDS = 30
MFA_TOTP_WINDOW_STEPS = 1  # accept the previous and next step (clock drift)

# ---- machine clients
API_CLIENT_LAST_USED_WRITE_INTERVAL_SECONDS = as_int(
    "API_CLIENT_LAST_USED_WRITE_INTERVAL_SECONDS", 60, minimum=1, maximum=3600
)

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
