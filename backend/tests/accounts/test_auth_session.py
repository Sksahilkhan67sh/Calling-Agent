"""Refresh rotation, reuse detection and logout over HTTP (P2-09)."""

from unittest import mock

import pytest
from django.core.cache import caches
from freezegun import freeze_time
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.roles import ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.audit import actions
from apps.audit.models import AuditEvent
from apps.core.throttles import LoginThrottle
from tests.accounts.helpers import LOGOUT, REFRESH, browser, cookie_value, login, post
from tests.accounts.test_mfa import make_device

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    pytest.mark.urls("tests.testapp.urls_with_auth"),
]


@pytest.fixture(autouse=True)
def _clean_throttle_cache():
    caches["default"].clear()


@pytest.fixture
def manager(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


@pytest.fixture
def session(manager, settings):
    """A logged-in browser: cookies for access, refresh and CSRF."""
    make_device(manager)  # MFA-enrolled: log in through the real flow
    from apps.accounts import mfa
    from apps.accounts.models import MfaDevice

    device = MfaDevice.objects.get(user=manager)
    seed = mfa._cipher().decrypt(device.secret_encrypted, context=mfa._context(device.pk))
    client = browser()
    assert login(client, manager.email, code=mfa.compute_code(seed, mfa.current_step())).status_code == 200
    return client


def cleared(response, settings) -> bool:
    return all(
        response.cookies[name]["max-age"] == 0 and response.cookies[name].value == ""
        for name in (settings.AUTH_ACCESS_COOKIE_NAME, settings.AUTH_REFRESH_COOKIE_NAME)
    )


# --- refresh -----------------------------------------------------------------------------------------


def test_refresh_rotates_both_cookies_and_keeps_the_session_alive(session, settings):
    old_refresh, old_access = (
        cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME),
        cookie_value(session, settings.AUTH_ACCESS_COOKIE_NAME),
    )
    response = post(session, settings, REFRESH)
    assert response.status_code == 200 and response.json() == {"authenticated": True}
    assert cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME) != old_refresh
    assert cookie_value(session, settings.AUTH_ACCESS_COOKIE_NAME) != old_access
    assert response["Cache-Control"] == "no-store" and response["Pragma"] == "no-cache"
    assert session.get("/whoami/").status_code == 200
    assert post(session, settings, REFRESH).status_code == 200  # and again: the chain continues


def test_refresh_past_the_absolute_cap_is_the_uniform_401_even_for_an_active_session(session, settings):
    twelve_hours, cap = 43200, settings.JWT_SESSION_ABSOLUTE_MAX_SECONDS
    with freeze_time() as clock:  # frozen at "now": the session started a moment ago
        for _ in range(cap // twelve_hours - 1):  # an active user refreshing twice a day stays logged in
            clock.tick(twelve_hours)
            assert post(session, settings, REFRESH).status_code == 200
        clock.tick(twelve_hours - 5)  # five seconds inside the cap (login happened just before the freeze)
        assert post(session, settings, REFRESH).status_code == 200
        clock.tick(10)  # five seconds past the cap, with a perfectly valid refresh token in hand
        response = post(session, settings, REFRESH)
    assert response.status_code == 401 and cleared(response, settings)
    assert response.json() == {"code": "invalid_credentials", "message": "Invalid credentials."}
    assert AuditEvent.objects.filter(action=actions.AUTH_SESSION_EXPIRED).count() == 1


def test_refresh_without_the_csrf_header_is_403_and_does_not_rotate(session, settings):
    refresh = cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME)
    response = session.post(REFRESH)  # a cross-site form post would look like this
    assert response.status_code == 403 and response.json() == {
        "code": "forbidden",
        "message": "The request was rejected.",
    }
    assert not BlacklistedToken.objects.exists()  # the token was never touched
    assert cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME) == refresh
    assert post(session, settings, REFRESH).status_code == 200  # still valid afterwards


def test_refresh_without_a_cookie_is_401_and_clears_cookies(settings):
    response = browser().post(REFRESH)
    assert response.status_code == 401 and cleared(response, settings)
    assert response.json() == {"code": "invalid_credentials", "message": "Invalid credentials."}


@pytest.mark.parametrize("junk", ["garbage", "a.b.c", "A" * 5000])
def test_refresh_with_a_bad_cookie_is_401(junk, settings):
    client = browser()
    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = junk
    client.cookies[settings.CSRF_COOKIE_NAME] = "x" * 32
    response = client.post(REFRESH, HTTP_X_CSRFTOKEN="x" * 32)
    assert response.status_code == 401 and cleared(response, settings)


def test_an_access_token_in_the_refresh_cookie_is_refused(manager, settings):
    client = browser()
    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = tokens.issue_tokens(manager).access
    client.cookies[settings.CSRF_COOKIE_NAME] = "y" * 32
    assert client.post(REFRESH, HTTP_X_CSRFTOKEN="y" * 32).status_code == 401


def test_expired_refresh_token_is_401(manager, settings):
    with freeze_time("2026-10-11 12:00:00") as clock:
        client = browser()
        make_device(manager)
        client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = tokens.issue_tokens(manager).refresh
        client.cookies[settings.CSRF_COOKIE_NAME] = "z" * 32
        clock.tick(86400 + 1)
        assert client.post(REFRESH, HTTP_X_CSRFTOKEN="z" * 32).status_code == 401


def test_replaying_a_rotated_refresh_token_is_theft_over_http(session, settings):
    stolen = cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME)
    assert post(session, settings, REFRESH).status_code == 200  # the victim rotates
    thief = browser()
    thief.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = stolen
    thief.cookies[settings.CSRF_COOKIE_NAME] = "t" * 32
    response = thief.post(REFRESH, HTTP_X_CSRFTOKEN="t" * 32)
    assert response.status_code == 401 and cleared(response, settings)
    assert response.json() == {
        "code": "invalid_credentials",
        "message": "Invalid credentials.",
    }  # no hint of theft
    assert (
        User.objects.get(
            email=AuditEvent.objects.get(action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED).actor_label
        ).auth_epoch
        == 1
    )
    assert session.get("/whoami/").status_code == 401  # the victim's access cookie died with the epoch
    assert post(session, settings, REFRESH).status_code == 401  # and so did their newest refresh token


def test_refresh_is_throttled_with_the_login_scope(session, settings, monkeypatch):
    # login and refresh share one bucket per client address; the fixture's login already used one request
    monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "3/min")
    assert post(session, settings, REFRESH).status_code == 200
    assert post(session, settings, REFRESH).status_code == 200
    blocked = post(session, settings, REFRESH)
    assert blocked.status_code == 429 and int(blocked["Retry-After"]) > 0


def test_body_mode_clients_send_the_refresh_token_in_the_body_without_csrf(manager, settings):
    settings.AUTH_TOKENS_IN_BODY = True
    make_device(manager)
    pair = tokens.issue_tokens(manager)
    client = browser()
    response = client.post(
        REFRESH, {"refresh": pair.refresh}, format="json"
    )  # no CSRF token: not an ambient credential
    assert response.status_code == 200 and response.json()["refresh"] != pair.refresh
    settings.AUTH_TOKENS_IN_BODY = False  # mode off: a body token is ignored entirely
    assert browser().post(REFRESH, {"refresh": response.json()["refresh"]}, format="json").status_code == 401


def test_refresh_rejects_unknown_body_fields_without_echoing_them(session, settings):
    response = post(session, settings, REFRESH, {"surprise_field": 1})
    assert response.status_code == 400 and "surprise_field" not in response.content.decode()


# --- logout ------------------------------------------------------------------------------------------


def test_logout_blacklists_the_refresh_token_clears_cookies_and_audits(session, manager, settings):
    refresh = cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME)
    response = post(session, settings, LOGOUT)
    assert response.status_code == 204 and cleared(response, settings) and response.content == b""
    assert response["Cache-Control"] == "no-store"
    assert BlacklistedToken.objects.filter(token__token=tokens.digest(refresh)).exists()
    assert AuditEvent.objects.filter(action=actions.AUTH_LOGOUT, object_id=str(manager.pk)).count() == 1


def test_the_old_refresh_token_is_dead_after_logout(session, settings):
    refresh = cookie_value(session, settings.AUTH_REFRESH_COOKIE_NAME)
    post(session, settings, LOGOUT)
    replay = browser()
    replay.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
    replay.cookies[settings.CSRF_COOKIE_NAME] = "r" * 32
    assert (
        replay.post(REFRESH, HTTP_X_CSRFTOKEN="r" * 32).status_code == 401
    )  # logout-then-reuse is detected too


def test_logout_requires_authentication_and_csrf(session, settings):
    assert browser().post(LOGOUT).status_code == 401
    assert session.post(LOGOUT).status_code == 403  # authenticated, but no CSRF header
    assert not BlacklistedToken.objects.exists()
    assert post(session, settings, LOGOUT).status_code == 204


def test_repeated_logout_with_a_still_valid_access_token_is_204(manager, settings):
    pair = tokens.issue_tokens(manager)
    for _ in range(3):  # a client that still holds the (not yet expired) credentials repeats the call
        client = browser()
        client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = pair.access
        client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = pair.refresh
        client.cookies[settings.CSRF_COOKIE_NAME] = "c" * 32
        assert client.post(LOGOUT, HTTP_X_CSRFTOKEN="c" * 32).status_code == 204
    assert BlacklistedToken.objects.count() == 1  # blacklisted once; repeated calls change nothing
    assert AuditEvent.objects.filter(action=actions.AUTH_LOGOUT).count() == 3  # every call is on record


def test_logout_with_a_garbage_refresh_cookie_still_succeeds(manager, settings):
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = tokens.issue_tokens(manager).access
    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = "garbage"
    client.cookies[settings.CSRF_COOKIE_NAME] = "g" * 32
    assert client.post(LOGOUT, HTTP_X_CSRFTOKEN="g" * 32).status_code == 204


def test_logout_never_revokes_someone_elses_refresh_token(manager, make_user, settings):
    other = make_user(ROLE_SALES_FOLLOW_UP)
    victim_pair = tokens.issue_tokens(other)
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = tokens.issue_tokens(manager).access
    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = victim_pair.refresh  # someone else's token
    client.cookies[settings.CSRF_COOKIE_NAME] = "v" * 32
    assert client.post(LOGOUT, HTTP_X_CSRFTOKEN="v" * 32).status_code == 204
    assert not BlacklistedToken.objects.exists()
    tokens.rotate_tokens(victim_pair.refresh)  # still perfectly usable by its owner


def test_logout_of_one_session_leaves_other_sessions_alone(manager, settings):
    make_device(manager)
    mine, other = tokens.issue_tokens(manager), tokens.issue_tokens(manager)
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = mine.access
    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = mine.refresh
    client.cookies[settings.CSRF_COOKIE_NAME] = "o" * 32
    assert client.post(LOGOUT, HTTP_X_CSRFTOKEN="o" * 32).status_code == 204
    assert tokens.rotate_tokens(other.refresh).refresh  # the other session survives


def test_body_mode_logout_with_bearer_and_body_refresh_token(manager, settings):
    settings.AUTH_TOKENS_IN_BODY = True
    pair = tokens.issue_tokens(manager)
    client = browser()
    response = client.post(
        LOGOUT, {"refresh": pair.refresh}, format="json", HTTP_AUTHORIZATION=f"Bearer {pair.access}"
    )
    assert response.status_code == 204 and BlacklistedToken.objects.count() == 1


def test_a_failed_audit_write_rolls_the_logout_back(manager, settings):
    from apps.audit.service import AuditError

    pair = tokens.issue_tokens(manager)
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = pair.access
    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = pair.refresh
    client.cookies[settings.CSRF_COOKIE_NAME] = "f" * 32
    with mock.patch("apps.accounts.views.record", side_effect=AuditError("down")):
        assert client.post(LOGOUT, HTTP_X_CSRFTOKEN="f" * 32).status_code == 500
    assert not BlacklistedToken.objects.exists()  # no audit, no logout: the refresh token is still live
