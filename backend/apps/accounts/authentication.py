"""DRF authentication classes. P2-08 adds the cookie-JWT and API-key classes here."""

from __future__ import annotations

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.mfa import EnrollmentTokenInvalid, read_enrollment_token
from apps.accounts.models import User


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
            raise AuthenticationFailed("Invalid credentials.") from None  # uniform, no detail
        return user, EnrollmentCredential()
