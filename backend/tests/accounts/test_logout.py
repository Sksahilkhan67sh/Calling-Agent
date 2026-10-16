"""POST /auth/logout (R4, OQ2-22): access cookie or refresh cookie, CSRF whenever a cookie is present,
always 204, audited only when a session was really ended."""

import pytest
from freezegun import freeze_time
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.roles import ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.audit import actions
from apps.audit.models import AuditEvent
from tests.accounts import forge
from tests.accounts.helpers import LOGOUT, browser

CSRF = "c" * 32
pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.testapp.urls_with_auth")]


@pytest.fixture
def manager(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


def client_with(settings, *, access: str | None = None, refresh: str | None = None):
    client = browser()
    if access:
        client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = access
    if refresh:
        client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
    client.cookies[settings.CSRF_COOKIE_NAME] = CSRF
    return client


def logout(client, *, csrf: str | None = CSRF):
    return client.post(LOGOUT, **({"HTTP_X_CSRFTOKEN": csrf} if csrf else {}))


def logouts() -> int:
    return AuditEvent.objects.filter(action=actions.AUTH_LOGOUT).count()


def assert_clean_204(response, settings):
    assert response.status_code == 204 and response.content == b""
    for name in (settings.AUTH_ACCESS_COOKIE_NAME, settings.AUTH_REFRESH_COOKIE_NAME):
        assert response.cookies[name]["max-age"] == 0 and response.cookies[name].value == ""
    assert response["Cache-Control"] == "no-store"


# --- which credential identifies the caller ------------------------------------------------------------


def test_with_both_cookies_the_session_is_ended_and_audited_once(manager, settings):
    pair = tokens.issue_tokens(manager)
    response = logout(client_with(settings, access=pair.access, refresh=pair.refresh))
    assert_clean_204(response, settings)
    assert BlacklistedToken.objects.count() == 1 and logouts() == 1
    event = AuditEvent.objects.get(action=actions.AUTH_LOGOUT)
    assert event.actor_id == manager.pk and event.metadata == {"identified_by": "access"}
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(pair.refresh)


def test_the_refresh_cookie_alone_logs_out_after_the_access_cookie_is_gone(manager, settings):
    pair = tokens.issue_tokens(manager)
    response = logout(client_with(settings, refresh=pair.refresh))
    assert_clean_204(response, settings)
    assert BlacklistedToken.objects.count() == 1 and logouts() == 1
    assert AuditEvent.objects.get(action=actions.AUTH_LOGOUT).metadata == {"identified_by": "refresh"}


def test_an_expired_access_cookie_falls_back_to_the_refresh_cookie(manager, settings):
    with freeze_time("2026-10-11 12:00:00") as clock:
        pair = tokens.issue_tokens(manager)
        clock.tick(901)  # access (15 min) is dead, refresh (1 day) is not
        response = logout(client_with(settings, access=pair.access, refresh=pair.refresh))
    assert_clean_204(response, settings)
    assert BlacklistedToken.objects.count() == 1 and logouts() == 1


def test_an_access_cookie_alone_clears_cookies_but_cannot_revoke_anything(manager, settings):
    response = logout(client_with(settings, access=tokens.issue_tokens(manager).access))
    assert_clean_204(response, settings)
    assert not BlacklistedToken.objects.exists() and logouts() == 0  # nothing was ended: nothing is audited


def test_no_credentials_at_all_is_still_204_and_needs_no_csrf(settings):
    client = browser()  # no cookies, no CSRF cookie, no header
    assert_clean_204(client.post(LOGOUT), settings)
    assert logouts() == 0


def test_a_refresh_cookie_with_the_wrong_owner_is_ignored(manager, make_user, settings):
    victim = tokens.issue_tokens(make_user(ROLE_SALES_FOLLOW_UP))
    response = logout(
        client_with(settings, access=tokens.issue_tokens(manager).access, refresh=victim.refresh)
    )
    assert_clean_204(response, settings)
    assert not BlacklistedToken.objects.exists() and logouts() == 0
    tokens.rotate_tokens(victim.refresh)  # still usable by its owner


def test_a_refresh_only_logout_ends_only_that_session_and_only_that_user(manager, make_user, settings):
    mine, other_session = tokens.issue_tokens(manager), tokens.issue_tokens(manager)
    someone = tokens.issue_tokens(make_user(ROLE_SALES_FOLLOW_UP))
    logout(client_with(settings, refresh=mine.refresh))
    assert (
        tokens.rotate_tokens(other_session.refresh).refresh and tokens.rotate_tokens(someone.refresh).refresh
    )
    assert tokens.read_access(other_session.access)[0] == manager


# --- credentials that must have no effect -------------------------------------------------------------


@pytest.mark.parametrize(
    "kind", ["expired", "tampered", "access-as-refresh", "never-issued", "stale-epoch", "past-cap"]
)
def test_bad_refresh_cookies_are_a_silent_noop(kind, manager, settings):
    pair = tokens.issue_tokens(manager)
    if kind == "expired":
        with freeze_time("2026-10-11 12:00:00") as clock:
            old = tokens.issue_tokens(manager)
            clock.tick(86401)
            response = logout(client_with(settings, refresh=old.refresh))
    else:
        refresh = {
            "tampered": pair.refresh[:-3] + ("AAA" if not pair.refresh.endswith("AAA") else "BBB"),
            "access-as-refresh": pair.access,
            "never-issued": forge.sign(forge.payload(manager, "refresh", lifetime=3600)),
            "stale-epoch": pair.refresh,
            "past-cap": forge.sign(forge.payload(manager, "refresh", lifetime=3600, sat=1)),
        }[kind]
        if kind == "stale-epoch":
            manager.bump_auth_epoch()
        response = logout(client_with(settings, refresh=refresh))
    assert_clean_204(response, settings)
    assert not BlacklistedToken.objects.exists() and logouts() == 0
    assert User.objects.get(pk=manager.pk).auth_epoch == (1 if kind == "stale-epoch" else 0)  # no escalation


def test_a_refresh_token_in_the_access_cookie_is_not_an_identity(manager, settings):
    pair = tokens.issue_tokens(manager)
    response = logout(client_with(settings, access=pair.refresh, refresh=pair.refresh))
    assert_clean_204(
        response, settings
    )  # the access cookie is junk, so the refresh cookie identifies the caller
    assert logouts() == 1
    assert AuditEvent.objects.get(action=actions.AUTH_LOGOUT).metadata == {"identified_by": "refresh"}


# --- CSRF ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cookies", ["access", "refresh", "both"])
@pytest.mark.parametrize("header", [None, "x" * 32])
def test_csrf_is_enforced_whenever_an_auth_cookie_is_present(cookies, header, manager, settings):
    pair = tokens.issue_tokens(manager)
    client = client_with(
        settings,
        access=pair.access if cookies in ("access", "both") else None,
        refresh=pair.refresh if cookies in ("refresh", "both") else None,
    )
    response = logout(client, csrf=header)  # missing header, or a header that does not match the cookie
    assert response.status_code == 403 and response.json() == {
        "code": "forbidden",
        "message": "The request was rejected.",
    }
    assert not BlacklistedToken.objects.exists() and logouts() == 0
    assert tokens.rotate_tokens(pair.refresh).refresh  # the session survived the forged request


def test_csrf_is_checked_before_any_token_is_read(settings):
    client = client_with(settings, refresh="not-even-a-token")
    assert logout(client, csrf=None).status_code == 403  # garbage and no header: 403, not a quiet 204


# --- idempotency, no leakage, theft ------------------------------------------------------------------


def test_a_second_logout_from_the_same_browser_is_a_quiet_204(manager, settings):
    pair = tokens.issue_tokens(manager)
    client = client_with(settings, access=pair.access, refresh=pair.refresh)
    assert logout(client).status_code == 204
    assert_clean_204(
        client.post(LOGOUT), settings
    )  # the browser dropped the cookies: nothing to send, no CSRF
    assert logouts() == 1 and User.objects.get(pk=manager.pk).auth_epoch == 0


def test_the_response_does_not_depend_on_whether_the_credential_was_valid(manager, make_user, settings):
    good = tokens.issue_tokens(manager)
    other = tokens.issue_tokens(make_user(ROLE_SALES_FOLLOW_UP))
    cases = [
        client_with(settings, refresh=good.refresh),  # valid: ends the session
        client_with(settings, refresh="garbage"),
        client_with(settings, refresh=other.refresh, access=tokens.issue_tokens(manager).access),  # foreign
        client_with(settings),  # no credentials
    ]
    seen = set()
    for client in cases:
        response = logout(client)
        seen.add(
            (
                response.status_code,
                response.content,
                tuple(
                    sorted(
                        (k, v["max-age"], v.value, v["path"])
                        for k, v in response.cookies.items()
                        if k != "csrftoken"
                    )
                ),
                response["Cache-Control"],
            )
        )
    assert len(seen) == 1  # identical, so the status cannot tell an attacker which credential worked


def test_a_rotated_token_replayed_on_logout_is_theft_and_revokes_every_session(manager, settings):
    first = tokens.issue_tokens(manager)
    second = tokens.rotate_tokens(first.refresh)
    response = logout(client_with(settings, refresh=first.refresh))
    assert_clean_204(response, settings)  # the caller still sees nothing unusual
    assert User.objects.get(pk=manager.pk).auth_epoch == 1
    assert AuditEvent.objects.filter(action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED).count() == 1
    assert logouts() == 0  # it was not a logout, it was a theft signal
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(second.access)  # the legitimate chain is dead too


def test_an_already_logged_out_token_replayed_is_treated_the_same(manager, settings):
    pair = tokens.issue_tokens(manager)
    assert logout(client_with(settings, refresh=pair.refresh)).status_code == 204
    assert logout(client_with(settings, refresh=pair.refresh)).status_code == 204
    assert logouts() == 1
    assert AuditEvent.objects.filter(action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED).count() == 1


def test_a_failed_audit_write_leaves_the_refresh_only_session_alive(manager, settings):
    from unittest import mock

    pair = tokens.issue_tokens(manager)
    client = client_with(settings, refresh=pair.refresh)
    client.raise_request_exception = False
    with mock.patch("apps.accounts.views.record", side_effect=RuntimeError("audit down")):
        assert logout(client).status_code == 500
    assert not BlacklistedToken.objects.exists()
    assert tokens.rotate_tokens(pair.refresh).refresh
