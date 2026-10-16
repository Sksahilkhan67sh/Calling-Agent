"""Production posture (Django-Backend-Design §4.4). Fails to start on unsafe or missing values."""

from apps.accounts.roles import MFA_MANDATORY_ROLES
from apps.core.settings_utils import ConfigError, as_int, as_origins, reject_placeholder

from .base import *  # noqa: F403
from .base import (
    CACHE_REDIS_URL,
    DATABASES,
    JWT_REFRESH_LIFETIME_SECONDS,
    JWT_SIGNING_KEY,
    MFA_REQUIRED_ROLES,
    SECRET_KEY,
)

DEBUG = False
ENABLE_API_DOCS = False

# Rates must be set deliberately from load-test results (Environment-Config §4).
API_RATE_LIMIT_PER_MINUTE = as_int("API_RATE_LIMIT_PER_MINUTE", minimum=1)
WEBHOOK_RATE_LIMIT_PER_MINUTE = as_int("WEBHOOK_RATE_LIMIT_PER_MINUTE", minimum=1)
LOGIN_RATE_LIMIT_PER_MINUTE = as_int("LOGIN_RATE_LIMIT_PER_MINUTE", minimum=1)
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(  # noqa: F405
    {
        "login": f"{LOGIN_RATE_LIMIT_PER_MINUTE}/min",
        "api-user": f"{API_RATE_LIMIT_PER_MINUTE}/min",
        "api-client": f"{API_RATE_LIMIT_PER_MINUTE}/min",
        "webhook": f"{WEBHOOK_RATE_LIMIT_PER_MINUTE}/min",
    }
)

if len(SECRET_KEY) < 50:
    raise ConfigError("DJANGO_SECRET_KEY must be at least 50 characters")
if JWT_SIGNING_KEY == SECRET_KEY:
    raise ConfigError("JWT_SIGNING_KEY must differ from DJANGO_SECRET_KEY")
if len(JWT_SIGNING_KEY) < 50:
    raise ConfigError("JWT_SIGNING_KEY must be at least 50 characters")
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

# The absolute session cap has no prod default and may not be shorter than one refresh token's life.
SESSION_ABSOLUTE_MAX_DAYS = as_int("SESSION_ABSOLUTE_MAX_DAYS", minimum=1, maximum=90)
JWT_SESSION_ABSOLUTE_MAX_SECONDS = SESSION_ABSOLUTE_MAX_DAYS * 86400
if JWT_SESSION_ABSOLUTE_MAX_SECONDS < JWT_REFRESH_LIFETIME_SECONDS:
    raise ConfigError("SESSION_ABSOLUTE_MAX_DAYS must not be shorter than JWT_REFRESH_LIFETIME_SECONDS")

# Lockout and proxy trust have no safe default: a wrong value either locks nobody or trusts spoofed addresses.
AXES_FAILURE_LIMIT = as_int("AXES_FAILURE_LIMIT", minimum=1)
TRUSTED_PROXY_COUNT = as_int("TRUSTED_PROXY_COUNT", minimum=0, maximum=10)

# Cookie auth means credentialed CORS: only for an explicit, HTTPS-only origin list.
CORS_ALLOWED_ORIGINS = as_origins("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = as_origins("CSRF_TRUSTED_ORIGINS")
if not all(origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS + CSRF_TRUSTED_ORIGINS):
    raise ConfigError("CORS_ALLOWED_ORIGINS and CSRF_TRUSTED_ORIGINS must use https://")
if not set(MFA_MANDATORY_ROLES) <= set(MFA_REQUIRED_ROLES):
    raise ConfigError("MFA_REQUIRED_ROLES must include Admin and Campaign Manager in production")

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
