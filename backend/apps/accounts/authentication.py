"""DRF authentication classes: cookie/bearer JWT, and the MFA enrolment credential. P2-12 adds API keys."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.mfa import EnrollmentTokenInvalid, read_enrollment_token
from apps.accounts.models import User
from apps.accounts.tokens import Claims, InvalidToken, read_access
from apps.core.logging import bind_context

_UNIFORM = "Invalid credentials."


@dataclass(frozen=True)
class AccessCredential:
    """``request.auth`` for a request authenticated by an access token."""

    jti: str
    via: str  # "cookie" or "bearer"
    access_expires_at: int  # epoch seconds
    session_expires_at: int  # epoch seconds: the absolute cap
    restricted = False


def _credential(claims: Claims, via: str) -> AccessCredential:
    return AccessCredential(claims.jti, via, int(claims.expires_at), claims.session_expires_at)


def enforce_csrf(request: Request) -> None:
    """Django's CSRF check (the same one DRF's SessionAuthentication uses) for unsafe methods."""
    SessionAuthentication().enforce_csrf(request)


class CookieJWTAuthentication(BaseAuthentication):
    """Authenticates the access token in the httpOnly cookie; CSRF is enforced for unsafe methods.

    ``Authorization: Bearer`` is honoured only when ``AUTH_TOKENS_IN_BODY`` is on (non-browser clients);
    otherwise the header is ignored. A Bearer credential is explicit, not ambient, so it needs no CSRF
    token, and if one is presented it must be valid: there is no fallback to the cookie.
    """

    def authenticate_header(self, request: Request) -> str:
        return 'Cookie realm="api"'

    def authenticate(self, request: Request) -> tuple[User, AccessCredential] | None:
        bearer = self._bearer(request) if settings.AUTH_TOKENS_IN_BODY else None
        if bearer is not None:
            user, claims = self._user_for(bearer)
            return user, _credential(claims, "bearer")
        raw = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE_NAME)
        if not raw:
            return None
        user, claims = self._user_for(raw)
        enforce_csrf(request)  # 403 on failure, after the token itself proved valid
        return user, _credential(claims, "cookie")

    @staticmethod
    def _bearer(request: Request) -> str | None:
        scheme, _, token = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
        return token.strip() if scheme.lower() == "bearer" else None

    @staticmethod
    def _user_for(raw: str) -> tuple[User, Claims]:
        try:
            user, claims = read_access(raw)
        except InvalidToken:
            raise AuthenticationFailed(_UNIFORM) from None
        bind_context(user_id=user.pk)
        return user, claims


class EnrollmentCredential:
    """``request.auth`` for a request authenticated by an MFA enrolment token.

    ``restricted`` makes ``HasCapability`` refuse it, so even a view that mistakenly lists this
    authenticator cannot grant the user's role capabilities.
    """

    restricted = True


class EnrollmentTokenAuthentication(BaseAuthentication):
    """``Authorization: MfaEnroll <token>``. Listed only on the two enrolment endpoints.

    A header, not a cookie: it is not an ambient credential, so it needs no CSRF protection, it lives for
    minutes, and it can only enrol an authenticator.
    """

    keyword = "MfaEnroll"

    def authenticate_header(self, request: Request) -> str:
        return self.keyword

    def authenticate(self, request: Request) -> tuple[User, EnrollmentCredential] | None:
        scheme, _, token = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
        if scheme.lower() != self.keyword.lower():
            return None  # not ours
        try:
            user = read_enrollment_token(token.strip())
        except EnrollmentTokenInvalid:
            raise AuthenticationFailed(_UNIFORM) from None  # uniform, no detail
        return user, EnrollmentCredential()


class CookieJWTScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    """OpenAPI description of the browser session: the access JWT travels in an httpOnly cookie."""

    target_class = "apps.accounts.authentication.CookieJWTAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):  # type: ignore[no-untyped-def]
        return {"type": "apiKey", "in": "cookie", "name": settings.AUTH_ACCESS_COOKIE_NAME}


class EnrollmentTokenScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    """OpenAPI description of the restricted MFA-enrolment credential (header, two endpoints only)."""

    target_class = "apps.accounts.authentication.EnrollmentTokenAuthentication"
    name = "enrollmentAuth"

    def get_security_definition(self, auto_schema):  # type: ignore[no-untyped-def]
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Restricted 'MfaEnroll <token>' credential for the two enrolment endpoints only.",
        }
