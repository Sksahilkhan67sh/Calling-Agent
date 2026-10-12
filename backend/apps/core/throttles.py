"""Scoped throttles (Backend Design §4.5). Rates come from settings, never from code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.cache import caches
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

if TYPE_CHECKING:
    from rest_framework.views import APIView


class _ScopedThrottle(SimpleRateThrottle):
    def __init__(self) -> None:
        # Resolve the cache per instance so settings overrides in tests apply.
        self.cache = caches["default"]
        super().__init__()

    def _identity(self, request: Request) -> str:
        return self.get_ident(request)

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self._identity(request)}


class LoginThrottle(_ScopedThrottle):
    scope = "login"  # per client address; stricter default, not load-derived


class ApiUserThrottle(_ScopedThrottle):
    scope = "api-user"

    def _identity(self, request: Request) -> str:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"user:{user.pk}"
        return self.get_ident(request)


class ApiClientThrottle(_ScopedThrottle):
    scope = "api-client"

    def _identity(self, request: Request) -> str:
        client_id = getattr(getattr(request, "auth", None), "client_id", None)
        return f"client:{client_id}" if client_id else self.get_ident(request)


class WebhookThrottle(_ScopedThrottle):
    scope = "webhook"
