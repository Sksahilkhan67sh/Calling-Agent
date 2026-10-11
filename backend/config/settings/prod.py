"""Production posture (Django-Backend-Design §4.4). Fails to start on unsafe or missing values."""

from apps.core.settings_utils import ConfigError, as_int, reject_placeholder

from .base import *  # noqa: F403
from .base import (
    CACHE_REDIS_URL,
    DATABASES,
    JWT_SIGNING_KEY,
    SECRET_KEY,
)

DEBUG = False
ENABLE_API_DOCS = False

# Rates must be set deliberately from load-test results (Environment-Config §4).
API_RATE_LIMIT_PER_MINUTE = as_int("API_RATE_LIMIT_PER_MINUTE", minimum=1)
WEBHOOK_RATE_LIMIT_PER_MINUTE = as_int("WEBHOOK_RATE_LIMIT_PER_MINUTE", minimum=1)
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(  # noqa: F405
    {
        "api-user": f"{API_RATE_LIMIT_PER_MINUTE}/min",
        "api-client": f"{API_RATE_LIMIT_PER_MINUTE}/min",
        "webhook": f"{WEBHOOK_RATE_LIMIT_PER_MINUTE}/min",
    }
)

if len(SECRET_KEY) < 50:
    raise ConfigError("DJANGO_SECRET_KEY must be at least 50 characters")
if JWT_SIGNING_KEY == SECRET_KEY:
    raise ConfigError("JWT_SIGNING_KEY must differ from DJANGO_SECRET_KEY")
if len(JWT_SIGNING_KEY) < 32:
    raise ConfigError("JWT_SIGNING_KEY must be at least 32 characters")
for _name, _value in {
    "DJANGO_SECRET_KEY": SECRET_KEY,
    "JWT_SIGNING_KEY": JWT_SIGNING_KEY,
    "PRIMARY_DB_URL": DATABASES["default"]["PASSWORD"],
    "CACHE_REDIS_URL": CACHE_REDIS_URL,
    "FIELD_ENCRYPTION_KEYS": ",".join(k for k, _ in FIELD_ENCRYPTION_KEYS),  # noqa: F405
}.items():
    reject_placeholder(_name, _value)
if DATABASES["default"]["OPTIONS"].get("sslmode") not in {"require", "verify-ca", "verify-full"}:
    raise ConfigError("PRIMARY_DB_URL must set sslmode to require, verify-ca or verify-full")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]  # in-cluster probes arrive without TLS
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
