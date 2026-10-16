"""CookieJWTAuthentication over HTTP: 401 bad tokens, 403 CSRF failures, Bearer only when enabled (P2-08)."""

import logging

import pytest
from django.middleware.csrf import _get_new_csrf_string
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.core import logging as lg
from tests.accounts import forge

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    pytest.mark.urls("tests.testapp.urls"),
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),
]


@pytest.fixture
def manager(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


def browser(settings, access: str | None = None, csrf: str | None = None) -> APIClient:
    """A client that enforces CSRF like a real browser session and carries the given cookies."""
    client = APIClient(enforce_csrf_checks=True)
    if access is not None:
        client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = access
    if csrf is not None:
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf
    return client


def good_cookie(user: User) -> str:
    return tokens.issue_tokens(user).access


# --- authentication ----------------------------------------------------------------------------------


def test_valid_cookie_authenticates_and_binds_the_user_to_the_log_context(manager, settings):
    response = browser(settings, good_cookie(manager)).get("/whoami/")
    assert response.status_code == 200
    assert response.json() == {
        "user": str(manager.pk),
        "via": "cookie",
        "user_id_in_log_context": str(manager.pk),
    }
    assert "user_id" not in lg.get_context()  # nothing leaks past the request


def test_no_cookie_is_unauthenticated_with_a_challenge(settings):
    response = browser(settings).get("/whoami/")
    assert response.status_code == 401 and response["WWW-Authenticate"].startswith("Cookie")


def test_the_refresh_cookie_is_not_an_access_credential(manager, settings):
    client = APIClient(enforce_csrf_checks=True)
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = tokens.issue_tokens(manager).refresh  # wrong type
    assert client.get("/whoami/").status_code == 401
    client2 = APIClient(enforce_csrf_checks=True)
    client2.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = tokens.issue_tokens(manager).refresh  # wrong cookie
    assert client2.get("/whoami/").status_code == 401


def forged_cookies(user: User) -> dict[str, str]:
    data = forge.payload(user)
    rs_token, public_pem = forge.rs256(data)
    return {
        "alg_none": forge.unsigned(data),
        "wrong_key": forge.sign(data, key="y" * 64),
        "rs256": rs_token,
        "key_confusion": forge.hs256_with_secret(data, public_pem),
        "tampered": forge.tamper_payload(good_cookie(user), sub="00000000-0000-4000-8000-000000000000"),
        "missing_exp": forge.sign(forge.payload(user, exp=...)),
        "missing_epoch": forge.sign(forge.payload(user, auth_epoch=...)),
        "wrong_audience": forge.sign(forge.payload(user, aud="x")),
        "garbage": "not-a-token",
    }


@pytest.mark.parametrize(
    "name",
    [
        "alg_none",
        "wrong_key",
        "rs256",
        "key_confusion",
        "tampered",
        "missing_exp",
        "missing_epoch",
        "wrong_audience",
        "garbage",
    ],
)
def test_forged_cookies_get_401(name, manager, settings):
    assert browser(settings, forged_cookies(manager)[name]).get("/whoami/").status_code == 401


def test_every_failure_looks_identical_to_the_client(manager, settings):
    fresh = good_cookie(manager)
    manager.bump_auth_epoch()  # `fresh` is now revoked
    bodies = {
        browser(settings, value).get("/whoami/").content
        for value in (fresh, "garbage", forge.unsigned(forge.payload(manager)), "A" * 5000)
    }
    assert len(bodies) == 1


def test_expired_cookie_gets_401(manager, settings):
    with freeze_time("2026-10-11 12:00:00") as clock:
        cookie = good_cookie(manager)
        clock.tick(901)
        assert browser(settings, cookie).get("/whoami/").status_code == 401


def test_epoch_mismatch_gets_401(manager, settings):
    cookie = good_cookie(manager)
    assert browser(settings, cookie).get("/whoami/").status_code == 200
    manager.bump_auth_epoch()
    assert browser(settings, cookie).get("/whoami/").status_code == 401


def test_deactivated_user_gets_401(manager, settings):
    cookie = good_cookie(manager)
    User.objects.filter(pk=manager.pk).update(is_active=False)
    assert browser(settings, cookie).get("/whoami/").status_code == 401


def test_a_forged_roles_claim_grants_nothing(make_user, settings):
    sales = make_user(ROLE_SALES_FOLLOW_UP)
    forged = forge.sign(forge.payload(sales, roles=[ROLE_ADMIN]))
    assert (
        browser(settings, forged).get("/whoami/").status_code == 403
    )  # authenticated, but Sales has no access
    assert browser(settings, forged).put("/retry-policy/").status_code in (403,)


def test_a_failed_authentication_never_logs_the_token(manager, settings, caplog):
    cookie = forge.flip_signature(good_cookie(manager))
    with caplog.at_level(logging.DEBUG):
        assert browser(settings, cookie).get("/whoami/").status_code == 401
    assert cookie not in caplog.text and cookie[:30] not in caplog.text


# --- CSRF --------------------------------------------------------------------------------------------


def test_unsafe_methods_need_the_csrf_token_under_cookie_auth(manager, settings):
    cookie, secret = good_cookie(manager), _get_new_csrf_string()
    no_header = browser(settings, cookie, secret).post("/whoami/")
    assert no_header.status_code == 403
    assert no_header.json() == {"code": "forbidden", "message": "The request was rejected."}  # no CSRF detail
    no_cookie = browser(settings, cookie).post("/whoami/", HTTP_X_CSRFTOKEN=secret)
    assert no_cookie.status_code == 403
    mismatch = browser(settings, cookie, secret).post("/whoami/", HTTP_X_CSRFTOKEN=_get_new_csrf_string())
    assert mismatch.status_code == 403
    assert browser(settings, cookie, secret).post("/whoami/", HTTP_X_CSRFTOKEN=secret).status_code == 200


@pytest.mark.parametrize("method", ["get", "head", "options"])
def test_safe_methods_need_no_csrf_token(method, manager, settings):
    response = getattr(browser(settings, good_cookie(manager)), method)("/whoami/")
    assert response.status_code in (200, 204)


def test_a_bad_cookie_is_401_before_csrf_is_considered(settings):
    assert browser(settings, "garbage").post("/whoami/").status_code == 401


def test_csrf_is_enforced_for_modifying_endpoints(manager, settings):
    cookie, secret = good_cookie(manager), _get_new_csrf_string()
    created = browser(settings, cookie, secret).post("/things/new/", {"title": "x"})
    assert created.status_code == 403
    assert (
        browser(settings, cookie, secret)
        .post("/things/new/", {"title": "x"}, HTTP_X_CSRFTOKEN=secret)
        .status_code
        == 201
    )


# --- Authorization: Bearer ---------------------------------------------------------------------------


def test_bearer_header_is_ignored_when_tokens_in_body_is_off(manager, settings):
    assert settings.AUTH_TOKENS_IN_BODY is False
    response = browser(settings).get("/whoami/", HTTP_AUTHORIZATION=f"Bearer {good_cookie(manager)}")
    assert response.status_code == 401


def test_bearer_header_works_without_csrf_when_enabled(manager, settings):
    settings.AUTH_TOKENS_IN_BODY = True
    client = browser(settings)
    token = good_cookie(manager)
    response = client.post(
        "/whoami/", HTTP_AUTHORIZATION=f"bearer {token}"
    )  # no CSRF token: not an ambient credential
    assert response.status_code == 200 and response.json()["via"] == "bearer"


def test_an_invalid_bearer_never_falls_back_to_a_valid_cookie(manager, settings):
    settings.AUTH_TOKENS_IN_BODY = True
    client = browser(settings, good_cookie(manager))
    assert client.get("/whoami/", HTTP_AUTHORIZATION="Bearer garbage").status_code == 401
    assert client.get("/whoami/", HTTP_AUTHORIZATION="Bearer ").status_code == 401


def test_a_valid_bearer_wins_over_the_cookie_and_other_schemes_are_ignored(manager, make_user, settings):
    settings.AUTH_TOKENS_IN_BODY = True
    other = make_user(ROLE_CAMPAIGN_MANAGER)
    client = browser(settings, good_cookie(manager))
    response = client.get("/whoami/", HTTP_AUTHORIZATION=f"Bearer {good_cookie(other)}")
    assert response.json()["user"] == str(other.pk)
    response = client.get("/whoami/", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")  # not ours: cookie is used
    assert response.json() == {
        "user": str(manager.pk),
        "via": "cookie",
        "user_id_in_log_context": str(manager.pk),
    }


def test_bearer_refresh_tokens_are_not_accepted(manager, settings):
    settings.AUTH_TOKENS_IN_BODY = True
    refresh = tokens.issue_tokens(manager).refresh
    assert browser(settings).get("/whoami/", HTTP_AUTHORIZATION=f"Bearer {refresh}").status_code == 401
