from django.conf import settings
from django.contrib.auth import authenticate
from django.middleware.csrf import get_token
from django_otp import match_token
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import record

from .authentication import ACCESS_COOKIE, REFRESH_COOKIE

REFRESH_PATH = "/v1/auth/"
_COOKIE = {"httponly": True, "samesite": "Strict"}


class Unauthorized(APIException):
    status_code = 401
    default_detail = "Authentication failed."
    default_code = "authentication_failed"


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)
    mfa_code = serializers.CharField(required=False)


def _set_cookies(response, access, refresh):
    response.set_cookie(
        ACCESS_COOKIE, access, max_age=int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        secure=settings.AUTH_COOKIE_SECURE, **_COOKIE,
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=REFRESH_PATH, secure=settings.AUTH_COOKIE_SECURE, **_COOKIE,
    )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        user = authenticate(request._request, username=d["username"], password=d["password"])
        if user is None:
            raise Unauthorized
        needs_mfa = user.is_superuser or user.groups.filter(name__in=settings.MFA_REQUIRED_ROLES).exists()
        # A required-role user with no enrolled device can never pass: safest fallback
        if needs_mfa and not (d.get("mfa_code") and match_token(user, d["mfa_code"])):
            record("auth.mfa_failed", "user", user.pk, actor=user, request=request)
            raise Unauthorized
        refresh = RefreshToken.for_user(user)
        record("auth.login", "user", user.pk, actor=user, request=request)
        response = Response({"detail": "ok"})
        _set_cookies(response, str(refresh.access_token), str(refresh))
        get_token(request._request)  # issues the CSRF cookie the dashboard echoes back
        return response


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if not raw:
            raise Unauthorized
        try:
            tokens = TokenRefreshSerializer().validate({"refresh": raw})
        except (TokenError, AuthenticationFailed):
            raise Unauthorized from None
        response = Response({"detail": "ok"})
        _set_cookies(response, tokens["access"], tokens["refresh"])
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # already expired or blacklisted: nothing left to revoke
        record("auth.logout", "user", request.user.pk, actor=request.user, request=request)
        response = Response(status=204)
        response.delete_cookie(ACCESS_COOKIE, samesite="Strict")
        response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, samesite="Strict")
        return response
