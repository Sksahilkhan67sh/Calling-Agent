"""Authentication cookies: names, flags and deletion (Django-Backend-Design §4.1).

Access cookie: HttpOnly, Secure, SameSite, Path=/, ``__Host-`` prefix (so it cannot be set by a sibling
subdomain or over HTTP). Refresh cookie: same flags but path-limited to the auth endpoints (so it is not
sent with ordinary API calls), hence ``__Secure-``: ``__Host-`` forbids a Path other than ``/``. The CSRF
cookie is Django's own (readable by the SPA for double-submit); ``rotate_csrf`` issues a fresh one at login.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from django.conf import settings
from django.http import HttpResponse
from django.middleware.csrf import rotate_token

from apps.accounts.tokens import TokenPair


def _flags() -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "domain": settings.AUTH_COOKIE_DOMAIN,
    }


def set_auth_cookies(response: HttpResponse, pair: TokenPair) -> None:
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE_NAME,
        pair.access,
        max_age=settings.JWT_ACCESS_LIFETIME_SECONDS,
        path="/",
        **_flags(),
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        pair.refresh,
        max_age=settings.JWT_REFRESH_LIFETIME_SECONDS,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        **_flags(),
    )


def clear_auth_cookies(response: HttpResponse) -> None:
    """Expire both cookies with the same path, domain, SameSite and Secure they were set with."""
    for name, path in (
        (settings.AUTH_ACCESS_COOKIE_NAME, "/"),
        (settings.AUTH_REFRESH_COOKIE_NAME, settings.AUTH_REFRESH_COOKIE_PATH),
    ):
        response.delete_cookie(
            name,
            path=path,
            domain=settings.AUTH_COOKIE_DOMAIN,
            samesite=cast(Literal["Lax", "Strict"], settings.AUTH_COOKIE_SAMESITE),  # validated in settings
        )


def rotate_csrf(request: Any) -> None:
    """Give the client a fresh CSRF token (the cookie is set by ``CsrfViewMiddleware`` on the response)."""
    rotate_token(request)


def no_store(response: HttpResponse) -> HttpResponse:
    """Responses that carry or revoke credentials must never be cached."""
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response
