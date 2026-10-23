import time
from unittest.mock import patch

import pytest
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.throttling import ScopedRateThrottle

from .conftest import LOGIN, PASSWORD, csrf

REFRESH = "/v1/auth/token/refresh"
LOGOUT = "/v1/auth/logout"


def totp_code(user):
    d = TOTPDevice.objects.get(user=user)
    t = TOTP(d.bin_key, d.step, d.t0, d.digits, d.drift)
    t.time = time.time()
    return f"{t.token():06d}"


def test_login_sets_httponly_cookies_and_csrf(make_user, login, client):
    make_user(role="Sales/Follow-up")
    r = login()
    assert r.status_code == 200
    for name in ("access_token", "refresh_token"):
        assert r.cookies[name]["httponly"] and r.cookies[name]["secure"]
        assert r.cookies[name]["samesite"] == "Strict"
    assert r.cookies["refresh_token"]["path"] == "/v1/auth/"
    assert "csrftoken" in r.cookies


def test_wrong_password_is_401(make_user, client):
    make_user()
    assert client.post(LOGIN, {"username": "u1", "password": "nope"}, format="json").status_code == 401


def test_mfa_role_needs_code(make_user, login):
    u = make_user(role="Admin")
    device = TOTPDevice.objects.create(user=u, confirmed=True)
    assert login().status_code == 401
    assert login(mfa_code="000000").status_code == 401
    device.refresh_from_db()
    assert device.throttling_failure_count == 1  # django-otp throttles guesses
    device.throttle_reset()
    assert login(mfa_code=totp_code(u)).status_code == 200


def test_mfa_role_without_device_cannot_login(make_user, login):
    make_user(role="Campaign Manager")
    assert login(mfa_code="123456").status_code == 401


def test_axes_lockout_blocks_correct_password(make_user, client, login):
    make_user()
    for _ in range(3):
        client.post(LOGIN, {"username": "u1", "password": "bad"}, format="json")
    assert login().status_code == 429


def test_login_throttled(make_user, login):
    from django.core.cache import cache

    cache.clear()
    with patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"login": "2/min"}):
        codes = [login().status_code for _ in range(3)]
    cache.clear()
    assert codes[-1] == 429


def test_refresh_rotates_and_old_token_is_rejected(make_user, login, client):
    make_user()
    old = login().cookies["refresh_token"].value
    r = client.post(REFRESH, **csrf(client))
    assert r.status_code == 200
    assert r.cookies["refresh_token"].value != old
    client.cookies["refresh_token"] = old
    assert client.post(REFRESH, **csrf(client)).status_code == 401


def test_refresh_requires_cookie_and_csrf(make_user, login, client):
    make_user()
    login()
    assert client.post(REFRESH).status_code == 403
    client.cookies.pop("refresh_token")
    assert client.post(REFRESH, **csrf(client)).status_code == 401


def test_refresh_rejected_for_deactivated_user(make_user, login, client):
    u = make_user()
    login()
    u.is_active = False
    u.save()
    assert client.post(REFRESH, **csrf(client)).status_code == 401


def test_logout_blacklists_refresh_and_enforces_csrf(make_user, login, client):
    make_user()
    login()
    assert client.post(LOGOUT).status_code == 403
    assert client.post(LOGOUT, **csrf(client)).status_code == 204
    assert client.cookies["access_token"].value == ""
    assert client.post(REFRESH, **csrf(client)).status_code == 401


def test_access_token_of_deactivated_user_rejected(make_user, login, client):
    u = make_user()
    login()
    u.is_active = False
    u.save()
    assert client.post(LOGOUT, **csrf(client)).status_code == 401


def test_logout_without_login_is_401(client, db):
    assert client.post(LOGOUT).status_code == 401
