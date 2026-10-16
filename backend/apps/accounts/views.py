"""Authentication endpoints (API contract: /auth/token, /auth/token/refresh, /auth/logout) plus the minimal
MFA-enrolment additions. Every response is uncacheable; failures are uniform."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import mfa
from apps.accounts.authentication import (
    AccessCredential,
    CookieJWTAuthentication,
    EnrollmentTokenAuthentication,
    enforce_csrf,
)
from apps.accounts.cookies import clear_auth_cookies, no_store, rotate_csrf, set_auth_cookies
from apps.accounts.login import check_credentials
from apps.accounts.models import User
from apps.accounts.parsers import BoundedJSONParser
from apps.accounts.permissions import IsEnrollmentCredential, IsHumanSession
from apps.accounts.serializers import (
    AuthenticatedSerializer,
    ErrorSerializer,
    MeSerializer,
    MfaConfirmSerializer,
    MfaEnrollResponseSerializer,
    RefreshBodySerializer,
    TokenRequestSerializer,
)
from apps.accounts.tokens import InvalidToken, TokenPair, issue_tokens, revoke_refresh, rotate_tokens
from apps.audit import actions
from apps.audit.models import Outcome
from apps.audit.service import Actor, record
from apps.core import error_codes
from apps.core.permissions import PublicEndpoint
from apps.core.throttles import ApiUserThrottle, LoginThrottle

logger = logging.getLogger(__name__)

_EMAIL_LIKE = re.compile(
    r"[^@\s]{1,64}@[^@\s]{1,255}"
)  # only an email-shaped value is kept as an audit label


def error(api_error: error_codes.ApiError) -> Response:
    return Response(api_error.body(), status=api_error.status)


class AuthAPIView(APIView):
    """JSON only, bounded body, uncacheable responses, and the contract's ``{code, message}`` errors."""

    parser_classes = [BoundedJSONParser]
    throttle_classes = [LoginThrottle]

    def finalize_response(self, request: Request, response: Response, *args: Any, **kwargs: Any) -> Response:
        return no_store(super().finalize_response(request, response, *args, **kwargs))  # type: ignore[return-value]


def _body(*, authenticated: bool, pair: TokenPair | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"authenticated": authenticated, **extra}
    if pair is not None and settings.AUTH_TOKENS_IN_BODY:  # non-browser clients only
        body["access"], body["refresh"] = pair.access, pair.refresh
    return body


def _start_session(request: Request, user: User, *, mfa_used: bool) -> Response:
    """Issue tokens and the audit event atomically: no event, no session (fail closed)."""
    with transaction.atomic():
        pair = issue_tokens(user)
        record(
            action=actions.AUTH_LOGIN_SUCCESS,
            actor=Actor.user(user),
            object_type="user",
            object_id=user.pk,
            metadata={"mfa": mfa_used},
        )
    response = Response(_body(authenticated=True, pair=pair, mfa_enrollment_required=False))
    set_auth_cookies(response, pair)
    rotate_csrf(request)  # fresh CSRF token for the new session (cookie set by CsrfViewMiddleware)
    return response


def _login_failed(raw_email: str, reason: str, target: User | None) -> None:
    label = (
        raw_email if _EMAIL_LIKE.fullmatch(raw_email) else ""
    )  # never store a password typed into the field
    with transaction.atomic():  # its own transaction: the failure must stay on record
        record(
            action=actions.AUTH_LOGIN_FAILURE,
            actor=Actor.anonymous(label),
            object_type="user" if target else "",
            object_id=target.pk if target else None,
            outcome=Outcome.FAILURE,
            metadata={"reason": reason},
        )


class LoginView(AuthAPIView):
    """POST /auth/token: password (+ MFA code) -> cookies. Any failure is the same 401."""

    authentication_classes: list[Any] = []
    permission_classes = [PublicEndpoint]

    @extend_schema(
        tags=["Auth"],
        summary="Log in (password + MFA code) and receive tokens",
        auth=[],
        request=TokenRequestSerializer,
        responses={
            200: OpenApiResponse(AuthenticatedSerializer, description="Authenticated"),
            400: OpenApiResponse(ErrorSerializer, description="Malformed request"),
            401: OpenApiResponse(ErrorSerializer, description="Invalid credentials or MFA code"),
            429: OpenApiResponse(ErrorSerializer, description="Too many attempts"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = TokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email, password = serializer.validated_data["username"], serializer.validated_data["password"]
        code = serializer.validated_data.get("mfa_code", "")

        check = check_credentials(email, password)
        reason, user = check.reason, check.user
        if user is not None and user.must_enroll_mfa:
            return self._enrolment_required(user)
        mfa_used = False
        if user is not None and user.has_active_mfa_device:
            mfa_used = True
            if not code:
                user, reason = None, "mfa_missing"
            elif not mfa.verify_login_code(
                user, code
            ):  # audits its own failure and enforces replay protection
                user, reason = None, "mfa_invalid"
        if user is None:
            _login_failed(email, reason, check.target)
            return error(error_codes.INVALID_CREDENTIALS)
        return _start_session(request, user, mfa_used=mfa_used)

    @staticmethod
    def _enrolment_required(user: User) -> Response:
        """Valid password, roles require MFA, none enrolled yet: hand out the restricted credential only."""
        with transaction.atomic():
            record(
                action=actions.AUTH_LOGIN_SUCCESS,
                actor=Actor.user(user),
                object_type="user",
                object_id=user.pk,
                metadata={"mfa": False, "enrollment_required": True},
            )
            token = mfa.issue_enrollment_token(user)
        return Response(
            {
                "authenticated": False,
                "mfa_enrollment_required": True,
                "mfa_enrollment_token": token,
                "expires_in": settings.MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS,
            }
        )


class RefreshView(AuthAPIView):
    """POST /auth/token/refresh: rotate the refresh token. CSRF is enforced for the cookie credential
    *before* the token is touched, so a cross-site request cannot rotate (and so sign out) a user."""

    authentication_classes: list[Any] = []
    permission_classes = [PublicEndpoint]

    @extend_schema(
        tags=["Auth"],
        summary="Rotate the refresh token and issue a new access token",
        auth=[],
        request=RefreshBodySerializer,
        responses={
            200: OpenApiResponse(AuthenticatedSerializer, description="New tokens issued"),
            401: OpenApiResponse(
                ErrorSerializer, description="Refresh token missing, expired, rotated or blacklisted"
            ),
            429: OpenApiResponse(ErrorSerializer, description="Too many attempts"),
        },
    )
    def post(self, request: Request) -> Response:
        body = RefreshBodySerializer(data=request.data if request.data else {})
        body.is_valid(raise_exception=True)
        raw = body.validated_data.get("refresh") if settings.AUTH_TOKENS_IN_BODY else None
        if not raw:  # ambient credential: the cookie
            raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
            if not raw:
                return self._rejected()
            enforce_csrf(request)
        try:
            pair = rotate_tokens(raw)
        except InvalidToken:  # includes reuse detection (already handled and audited inside)
            return self._rejected()
        response = Response(_body(authenticated=True, pair=pair))
        set_auth_cookies(response, pair)
        return response

    @staticmethod
    def _rejected() -> Response:
        response = error(error_codes.INVALID_CREDENTIALS)
        clear_auth_cookies(response)
        return response


class LogoutView(AuthAPIView):
    """POST /auth/logout: blacklist the caller's refresh token, clear cookies. Idempotent."""

    throttle_classes = list(APIView.throttle_classes)  # the default per-user throttle, not the login scope
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Blacklist the refresh token and clear cookies",
        request=RefreshBodySerializer,
        responses={
            204: OpenApiResponse(description="Logged out"),
            401: OpenApiResponse(ErrorSerializer, description="Not authenticated"),
        },
    )
    def post(self, request: Request) -> Response:
        body = RefreshBodySerializer(data=request.data if request.data else {})
        body.is_valid(raise_exception=True)
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw and settings.AUTH_TOKENS_IN_BODY:
            raw = body.validated_data.get("refresh")
        with transaction.atomic():
            if raw:
                revoke_refresh(raw, user_id=cast(User, request.user).pk)  # only the caller's own token
            record(
                action=actions.AUTH_LOGOUT,
                actor=Actor.user(request.user),
                object_type="user",
                object_id=request.user.pk,
            )
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class CsrfView(AuthAPIView):
    """GET /auth/csrf: ensure the browser holds a CSRF cookie (e.g. after the cookie jar was cleared)."""

    authentication_classes: list[Any] = []
    permission_classes = [PublicEndpoint]
    throttle_classes = list(APIView.throttle_classes)

    @extend_schema(
        tags=["Auth"],
        summary="Ensure the CSRF cookie is set",
        auth=[],
        responses={204: OpenApiResponse(description="CSRF cookie set")},
    )
    def get(self, request: Request) -> Response:
        get_token(request)  # marks the cookie for (re)issue by CsrfViewMiddleware
        return Response(status=status.HTTP_204_NO_CONTENT)


class _EnrolmentView(AuthAPIView):
    authentication_classes = [EnrollmentTokenAuthentication]
    permission_classes = [IsEnrollmentCredential]


class MfaEnrollView(_EnrolmentView):
    """POST /auth/mfa/enroll: returns the secret and provisioning URI once."""

    @extend_schema(
        tags=["Auth"],
        summary="Begin MFA enrolment (enrolment credential only)",
        request=None,
        responses={
            200: OpenApiResponse(
                MfaEnrollResponseSerializer, description="Secret and provisioning URI, shown once"
            ),
            401: OpenApiResponse(ErrorSerializer, description="Invalid enrolment credential"),
            409: OpenApiResponse(ErrorSerializer, description="Enrolment not available"),
        },
    )
    def post(self, request: Request) -> Response:
        try:
            enrollment = mfa.begin_enrollment(cast(User, request.user))
        except mfa.MfaError:
            return error(error_codes.ENROLLMENT_UNAVAILABLE)
        return Response(
            {
                "secret": enrollment.secret,
                "provisioning_uri": enrollment.provisioning_uri,
                "issuer": settings.MFA_ISSUER_NAME,
            }
        )


class MfaConfirmView(_EnrolmentView):
    """POST /auth/mfa/confirm: a valid code activates the authenticator and starts the session."""

    @extend_schema(
        tags=["Auth"],
        summary="Confirm MFA enrolment with a code and start the session",
        request=MfaConfirmSerializer,
        responses={
            200: OpenApiResponse(AuthenticatedSerializer, description="Authenticated"),
            400: OpenApiResponse(ErrorSerializer, description="Invalid code"),
            401: OpenApiResponse(ErrorSerializer, description="Invalid enrolment credential"),
            409: OpenApiResponse(ErrorSerializer, description="No enrolment in progress"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = MfaConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = cast(User, request.user)
        try:
            mfa.confirm_enrollment(user, serializer.validated_data["code"])
        except mfa.NoPendingEnrollment:
            return error(error_codes.NO_ENROLLMENT)
        except mfa.InvalidCode:
            return error(error_codes.INVALID_CODE)
        return _start_session(request, User.objects.get(pk=user.pk), mfa_used=True)  # epoch moved: reload


class MeView(AuthAPIView):
    """GET /auth/me: who is signed in, for the single-page app (identity, roles, capabilities, MFA, session).

    Open to any human with a full session (no capability needed to read your own identity). The enrolment
    authenticator is listed only so a restricted credential is answered with 403 instead of looking anonymous.
    """

    authentication_classes = [CookieJWTAuthentication, EnrollmentTokenAuthentication]
    permission_classes = [IsHumanSession]
    throttle_classes = [ApiUserThrottle]

    @extend_schema(
        tags=["Auth"],
        summary="The signed-in user: roles, capabilities, MFA state and session expiry",
        responses={
            200: OpenApiResponse(MeSerializer, description="Current user"),
            401: OpenApiResponse(ErrorSerializer, description="Not authenticated"),
            403: OpenApiResponse(ErrorSerializer, description="Not a full human session"),
            429: OpenApiResponse(ErrorSerializer, description="Too many requests"),
        },
    )
    def get(self, request: Request) -> Response:
        user: User = request.user  # type: ignore[assignment]  # IsHumanSession guarantees a User
        credential: AccessCredential = request.auth  # type: ignore[assignment]
        logger.info("identity read", extra={"user_id": str(user.pk)})
        payload = {
            "id": user.pk,
            "email": user.email,
            "full_name": user.full_name,
            "roles": sorted(user.role_names()),
            "capabilities": sorted(user.capabilities()),  # from the registry; is_superuser adds nothing
            "mfa": {"required": user.requires_mfa, "enrolled": user.has_active_mfa_device},
            "session": {
                "access_expires_at": datetime.fromtimestamp(credential.access_expires_at, UTC),
                "absolute_expires_at": datetime.fromtimestamp(credential.session_expires_at, UTC),
            },
        }
        return Response(MeSerializer(payload).data)
