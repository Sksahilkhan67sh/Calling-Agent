"""Shared helpers for the authentication endpoint tests."""

from rest_framework.test import APIClient

from apps.accounts import mfa
from tests.accounts.conftest import PASSWORD

TOKEN = "/v1/auth/token"
REFRESH = "/v1/auth/token/refresh"
LOGOUT = "/v1/auth/logout"
CSRF = "/v1/auth/csrf"
ENROLL = "/v1/auth/mfa/enroll"
CONFIRM = "/v1/auth/mfa/confirm"


def browser() -> APIClient:
    """A client that keeps cookies and enforces CSRF like a real browser."""
    return APIClient(enforce_csrf_checks=True)


def login(client: APIClient, email: str, password: str = PASSWORD, code: str | None = None):
    data = {"username": email, "password": password}
    if code is not None:
        data["mfa_code"] = code
    return client.post(TOKEN, data, format="json")


def csrf_token(client: APIClient, settings) -> str:
    return client.cookies[settings.CSRF_COOKIE_NAME].value


def post(client: APIClient, settings, path: str, data=None, **extra):
    """An unsafe request with the CSRF header a browser SPA would send."""
    return client.post(path, data, format="json", HTTP_X_CSRFTOKEN=csrf_token(client, settings), **extra)


def totp(seed: str, ahead: int = 0) -> str:
    return mfa.compute_code(seed, mfa.current_step() + ahead)


def cookie_value(client: APIClient, name: str) -> str:
    return client.cookies[name].value
