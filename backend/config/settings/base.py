import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from kombu import Queue

env = os.environ
BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = env["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = env["DJANGO_ALLOWED_HOSTS"].split(",")
ROOT_URLCONF = "config.urls"
ADMIN_ENABLED = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "apps.accounts",
    "apps.audit",
    "apps.campaigns",
    "apps.contacts",
    "apps.suppression",
    "apps.voice_runtime",
    "apps.calls",
    "apps.dialer",
    "apps.webhooks",
    "apps.recovery",
    "apps.analysis",
    "apps.dashboard_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.parse(env["PRIMARY_DB_URL"])
    | {"OPTIONS": {"pool": {"max_size": int(env["PRIMARY_DB_POOL_SIZE"])}}}
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
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

# Admin and Campaign Manager always need MFA; the env var can only add roles
MFA_REQUIRED_ROLES = {"Admin", "Campaign Manager"} | set(
    filter(None, env.get("MFA_REQUIRED_ROLES", "").split(","))
)

AXES_FAILURE_LIMIT = int(env["AXES_FAILURE_LIMIT"])
AXES_COOLOFF_TIME = timedelta(minutes=int(env.get("AXES_COOLOFF_MINUTES", "15")))
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
TRUSTED_PROXY_COUNT = int(env.get("TRUSTED_PROXY_COUNT", "0"))
AXES_IPWARE_PROXY_COUNT = TRUSTED_PROXY_COUNT

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=int(env.get("JWT_ACCESS_LIFETIME_SECONDS", "900"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": env["JWT_SIGNING_KEY"],
}
AUTH_COOKIE_SECURE = True

FIELD_ENCRYPTION_KEYS = env["FIELD_ENCRYPTION_KEYS"].split(",")  # newest first; older keys only decrypt
PHONE_HMAC_KEY = env["PHONE_HMAC_KEY"].encode()
CONTACT_IMPORT_MAX_BYTES = 10 * 1024 * 1024

CORS_ALLOWED_ORIGINS = env["CORS_ALLOWED_ORIGINS"].split(",")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

_rate = f"{int(env['API_RATE_LIMIT_PER_MINUTE'])}/min"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.CookieJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.core.permissions.RolePermission",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.core.throttles.ApiUserThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"api-user": _rate, "login": _rate, "webhook": f"{int(env['WEBHOOK_RATE_LIMIT_PER_MINUTE'])}/min"},
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
}

DOGRAH_BASE_URL = env["DOGRAH_BASE_URL"]
DOGRAH_API_KEY = env["DOGRAH_API_KEY"]
DOGRAH_REQUEST_TIMEOUT_SECONDS = int(env["DOGRAH_REQUEST_TIMEOUT_SECONDS"])
DOGRAH_DEFAULT_MODEL_CONFIG_UUID = env.get("DOGRAH_DEFAULT_MODEL_CONFIG_UUID") or None
DOGRAH_ALLOWED_ARTIFACT_HOSTS = [h for h in env["DOGRAH_ALLOWED_ARTIFACT_HOSTS"].split(",") if h]
DOGRAH_MAX_ARTIFACT_BYTES = int(env["DOGRAH_MAX_ARTIFACT_BYTES"])
DOGRAH_ARTIFACT_DEADLINE_SECONDS = int(env["DOGRAH_ARTIFACT_DEADLINE_SECONDS"])
# [verify] Dograh run-lookup and Agents API paths are not in the docs; no guessed defaults
DOGRAH_RUN_PATH = env["DOGRAH_RUN_PATH"]
DOGRAH_WORKFLOW_PATH = env["DOGRAH_WORKFLOW_PATH"]
PUBLIC_BASE_URL = env["PUBLIC_BASE_URL"].rstrip("/")
DOGRAH_WEBHOOK_SECRET = env["DOGRAH_WEBHOOK_SECRET"]
DOGRAH_WEBHOOK_SECRET_PREVIOUS = env.get("DOGRAH_WEBHOOK_SECRET_PREVIOUS", "")  # only during rotation
DOGRAH_WEBHOOK_HEADER_NAME = env.get("DOGRAH_WEBHOOK_HEADER_NAME", "X-Dograh-Webhook-Secret")
DOGRAH_EFFECTIVE_CONCURRENCY = int(env["DOGRAH_EFFECTIVE_CONCURRENCY"])
# [verify] Dograh disposition values for a normally completed conversation are not in the docs; anything else is a drop
DOGRAH_COMPLETED_DISPOSITIONS = [d for d in env["DOGRAH_COMPLETED_DISPOSITIONS"].split(",") if d]
RECONCILE_CEILING_SECONDS = int(env["RECONCILE_CEILING_SECONDS"])
OBJECT_STORAGE_BUCKET = env["OBJECT_STORAGE_BUCKET"]
OBJECT_STORAGE_ENDPOINT_URL = env.get("OBJECT_STORAGE_ENDPOINT_URL") or None  # S3-compatible backends only
RECORDING_URL_TTL_SECONDS = int(env["RECORDING_URL_TTL_SECONDS"])
RETENTION_DAYS = int(env["RETENTION_DAYS"])  # legal/compliance decision per Data Privacy; no guessed default

CELERY_BROKER_URL = env["CALL_QUEUE_BROKER_URL"]
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_TIME_LIMIT = 90
CELERY_TASK_IGNORE_RESULT = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_BEAT_SCHEDULE = {
    "dispatch-due": {"task": "apps.dialer.tasks.dispatch_due", "schedule": 10.0},
    "sweep-retention": {"task": "apps.recovery.tasks.sweep_retention", "schedule": 86400.0},
    "sweep-unanalyzed": {"task": "apps.analysis.tasks.sweep_unanalyzed", "schedule": 300.0},
    "reconcile-stuck": {"task": "apps.calls.tasks.reconcile_stuck", "schedule": 60.0},
}
CELERY_TASK_QUEUES = [Queue(q) for q in ("default", "dial", "webhook", "recovery", "analysis")]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.RedactingJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env.get("LOG_LEVEL", "INFO")},
}
