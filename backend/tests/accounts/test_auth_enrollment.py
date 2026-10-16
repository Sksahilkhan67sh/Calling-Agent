"""MFA enrolment over HTTP: login -> restricted credential -> enrol -> confirm -> session (P2-09)."""

import json
import logging

import pytest
from django.core.cache import caches

from apps.accounts import mfa
from apps.accounts.models import MfaDevice, User
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.audit import actions
from apps.audit.models import AuditEvent
from apps.core.throttles import LoginThrottle
from tests.accounts.helpers import CONFIRM, ENROLL, browser, login, totp

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    pytest.mark.urls("tests.testapp.urls_with_auth"),
]


@pytest.fixture(autouse=True)
def _clean_throttle_cache(monkeypatch):
    # The flows below make many requests from one address; the dedicated throttle test sets its own rate.
    monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "1000/min")
    caches["default"].clear()


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"MfaEnroll {token}"}


def enrolment_login(user, client=None):
    client = client or browser()
    response = login(client, user.email)
    return client, response


@pytest.mark.parametrize("role", [ROLE_CAMPAIGN_MANAGER, ROLE_ADMIN])
def test_users_who_must_enrol_get_a_restricted_credential_and_no_session(role, make_user, settings):
    user = make_user(role)
    client, response = enrolment_login(user)
    body = response.json()
    assert (
        response.status_code == 200
        and body["authenticated"] is False
        and body["mfa_enrollment_required"] is True
    )
    assert body["expires_in"] == 600 and body["mfa_enrollment_token"]
    assert not client.cookies  # no session cookies, no CSRF cookie: nothing but the credential
    assert response["Cache-Control"] == "no-store"
    event = AuditEvent.objects.get(action=actions.AUTH_LOGIN_SUCCESS)
    assert event.metadata == {"mfa": False, "enrollment_required": True}


def test_wrong_password_never_yields_an_enrolment_credential(make_user):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    response = login(browser(), user.email, password="not-the-password-1")
    assert response.status_code == 401 and "mfa_enrollment_token" not in response.content.decode()


def test_roles_without_mfa_get_a_normal_session_instead(make_user):
    body = login(browser(), make_user(ROLE_SALES_FOLLOW_UP).email).json()
    assert body["authenticated"] is True and "mfa_enrollment_token" not in body


def test_full_enrolment_flow_ends_in_a_session_and_future_logins_need_a_code(make_user, settings):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)
    token = response.json()["mfa_enrollment_token"]

    begun = client.post(ENROLL, **bearer(token))
    assert begun.status_code == 200 and begun["Cache-Control"] == "no-store"
    secret = begun.json()["secret"]
    assert begun.json()["issuer"] == "AI Calling Agent" and begun.json()["provisioning_uri"].startswith(
        "otpauth://totp/"
    )

    wrong = client.post(CONFIRM, {"code": "000000"}, format="json", **bearer(token))
    assert wrong.status_code == 400 and wrong.json() == {
        "code": "invalid_code",
        "message": "The code is not valid.",
    }
    assert not client.cookies  # still no session

    confirmed = client.post(CONFIRM, {"code": totp(secret)}, format="json", **bearer(token))
    assert confirmed.status_code == 200 and confirmed.json() == {
        "authenticated": True,
        "mfa_enrollment_required": False,
    }
    assert (
        client.cookies[settings.AUTH_ACCESS_COOKIE_NAME].value
        and client.cookies[settings.CSRF_COOKIE_NAME].value
    )
    assert client.get("/whoami/").json()["user"] == str(user.pk)  # the session works
    assert User.objects.get(pk=user.pk).auth_epoch == 1 and User.objects.get(pk=user.pk).has_active_mfa_device
    assert AuditEvent.objects.filter(action=actions.AUTH_MFA_ENROLLED).count() == 1

    # from now on a code is required, and the enrolment code cannot be replayed
    assert login(browser(), user.email).status_code == 401
    assert (
        login(browser(), user.email, code=totp(secret)).status_code == 401
    )  # same step as enrolment: replay
    assert login(browser(), user.email, code=totp(secret, ahead=1)).status_code == 200


def test_the_credential_is_dead_once_enrolment_is_confirmed(make_user):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)
    token = response.json()["mfa_enrollment_token"]
    secret = client.post(ENROLL, **bearer(token)).json()["secret"]
    client.post(CONFIRM, {"code": totp(secret)}, format="json", **bearer(token))
    for path in (ENROLL, CONFIRM):
        again = browser().post(path, {"code": "123456"}, format="json", **bearer(token))
        assert again.status_code == 401 and again["WWW-Authenticate"] == "MfaEnroll"


def test_beginning_twice_replaces_the_pending_device(make_user):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)
    token = response.json()["mfa_enrollment_token"]
    first = client.post(ENROLL, **bearer(token)).json()["secret"]
    second = client.post(ENROLL, **bearer(token)).json()["secret"]
    assert first != second and MfaDevice.objects.filter(user=user, disabled_at__isnull=False).count() == 1
    stale = client.post(CONFIRM, {"code": totp(first)}, format="json", **bearer(token))
    assert stale.status_code == 400  # the replaced secret confirms nothing
    assert client.post(CONFIRM, {"code": totp(second)}, format="json", **bearer(token)).status_code == 200


def test_confirm_without_beginning_is_409(make_user):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)
    done = client.post(
        CONFIRM, {"code": "123456"}, format="json", **bearer(response.json()["mfa_enrollment_token"])
    )
    assert done.status_code == 409 and done.json()["code"] == "no_enrollment"


def test_the_enrolment_endpoints_refuse_everything_but_the_restricted_credential(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    session = browser()
    login(session, user.email)  # a perfectly good session
    for path in (ENROLL, CONFIRM):
        response = session.post(
            path,
            {"code": "123456"},
            format="json",
            HTTP_X_CSRFTOKEN=session.cookies[settings.CSRF_COOKIE_NAME].value,
        )
        assert response.status_code == 401 and response["WWW-Authenticate"] == "MfaEnroll"
    assert browser().post(ENROLL).status_code == 401


@pytest.mark.parametrize("header", ["MfaEnroll garbage", "MfaEnroll ", "MfaEnroll", "Bearer garbage"])
def test_bad_credentials_are_a_uniform_401(header):
    response = browser().post(ENROLL, HTTP_AUTHORIZATION=header)
    assert response.status_code == 401 and response["WWW-Authenticate"] == "MfaEnroll"


def test_the_enrolment_token_does_not_work_on_session_endpoints(make_user, settings):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    _, response = enrolment_login(user)
    token = response.json()["mfa_enrollment_token"]
    client = browser()
    for path in ("/whoami/", "/things/", "/retry-policy/"):
        assert client.get(path, **bearer(token)).status_code in (401, 403)
    settings.AUTH_TOKENS_IN_BODY = True  # even where Bearer is honoured, this is not an access token
    assert client.get("/whoami/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 401


def test_enrolment_endpoints_share_the_login_throttle(make_user, monkeypatch):
    monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "3/min")
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)  # 1
    token = response.json()["mfa_enrollment_token"]
    assert client.post(ENROLL, **bearer(token)).status_code == 200  # 2
    assert client.post(ENROLL, **bearer(token)).status_code == 200  # 3
    assert client.post(ENROLL, **bearer(token)).status_code == 429


def test_wrong_confirmation_codes_are_audited_but_never_logged(make_user, caplog):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)
    token = response.json()["mfa_enrollment_token"]
    secret = client.post(ENROLL, **bearer(token)).json()["secret"]
    with caplog.at_level(logging.DEBUG):
        client.post(CONFIRM, {"code": "135790"}, format="json", **bearer(token))
        client.post(CONFIRM, {"code": totp(secret)}, format="json", **bearer(token))
    everything = caplog.text + json.dumps(
        list(AuditEvent.objects.values("before", "after", "metadata", "actor_label")), default=str
    )
    assert secret not in everything and token not in everything and "135790" not in everything
    assert "otpauth" not in everything
    assert AuditEvent.objects.filter(action=actions.AUTH_MFA_FAILED).count() == 1


def test_enrolment_that_becomes_unavailable_midway_is_a_409(make_user):
    from unittest import mock

    user = make_user(ROLE_CAMPAIGN_MANAGER)
    client, response = enrolment_login(user)
    token = response.json()["mfa_enrollment_token"]
    with mock.patch("apps.accounts.views.mfa.begin_enrollment", side_effect=mfa.AlreadyEnrolled("raced")):
        done = client.post(ENROLL, **bearer(token))
    assert done.status_code == 409 and done.json() == {
        "code": "enrollment_unavailable",
        "message": "Enrolment is not available.",
    }
