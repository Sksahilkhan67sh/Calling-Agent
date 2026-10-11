from apps.core.logging import build_logging_config

from .base import *  # noqa: F403

DEBUG = True
ENABLE_API_DOCS = True
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
LOGGING = build_logging_config(level="DEBUG", pretty=True, extra_sensitive_keys=(DOGRAH_WEBHOOK_HEADER_NAME,))  # noqa: F405
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
