from apps.core.logging import build_logging_config

from .base import *  # noqa: F403
from .base import AUTH_COOKIE_DOMAIN, cookie_names

DEBUG = True
ENABLE_API_DOCS = True
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]
AUTH_COOKIE_SECURE = False  # plain-HTTP localhost; prefixed cookie names need Secure
AUTH_ACCESS_COOKIE_NAME, AUTH_REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(
    secure=AUTH_COOKIE_SECURE, domain=AUTH_COOKIE_DOMAIN
)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
LOGGING = build_logging_config(level="DEBUG", pretty=True, extra_sensitive_keys=(DOGRAH_WEBHOOK_HEADER_NAME,))  # noqa: F405
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
