"""GET /auth/me (R3, OQ2-21): identity for the single-page app, humans only, nothing extra."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import caches
from freezegun import freeze_time
from rest_framework.test import APIRequestFactory

from apps.accounts import mfa, tokens
from apps.accounts.models import User
from apps.accounts.permissions import IsHumanSession
from apps.accounts.roles import (
    ROLE_ADMIN,
    ROLE_CAMPAIGN_MANAGER,
    ROLE_CAPABILITIES,
    ROLE_SALES_FOLLOW_UP,
)
from apps.audit.models import AuditEvent
from apps.core.throttles import ApiUserThrottle, LoginThrottle
from tests.accounts.helpers import browser
from tests.accounts.test_mfa import make_device

ME = "/v1/auth/me"
UNIFORM_401 = {"code": "invalid_credentials", "message": "Invalid credentials."}
FORBIDDEN_403 = {"code": "forbidden", "message": "The request was rejected."}
TOP_LEVEL = {"id", "email", "full_name", "roles", "capabilities", "mfa", "session"}

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.testapp.urls_with_auth")]


@pytest.fixture(autouse=True)
def _clean_throttle_cache():
    caches["default"].clear()


def signed_in(user: User, settings):
    """A browser holding a genuine access cookie for ``user`` (what a completed login leaves behind)."""
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = tokens.issue_tokens(user).access
    return client


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_returns_exactly_the_documented_fields(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP, full_name="Sam Seller")
    response = signed_in(user, settings).get(ME)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == TOP_LEVEL  # nothing else: no hash, epoch, jti, other ids
    assert set(body["mfa"]) == {"required", "enrolled"}
    assert set(body["session"]) == {"access_expires_at", "absolute_expires_at"}
    assert body["id"] == str(user.pk) and body["email"] == user.email and body["full_name"] == "Sam Seller"
    assert body["roles"] == [ROLE_SALES_FOLLOW_UP]
    assert response["Cache-Control"] == "no-store" and response["Pragma"] == "no-cache"
    assert response["Content-Type"].startswith("application/json")


@pytest.mark.parametrize("role", sorted(ROLE_CAPABILITIES))
def test_capabilities_of_each_role_match_the_rbac_matrix(role, make_user, settings):
    body = signed_in(make_user(role), settings).get(ME).json()
    assert body["capabilities"] == sorted(ROLE_CAPABILITIES[role])
    assert body["roles"] == [role]


def test_per_user_grants_are_part_of_the_effective_set(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    extra = "campaigns.create"
    assert extra not in ROLE_CAPABILITIES[ROLE_SALES_FOLLOW_UP]
    user.user_permissions.add(Permission.objects.get(content_type__app_label="accounts", codename=extra))
    body = signed_in(User.objects.get(pk=user.pk), settings).get(ME).json()
    assert extra in body["capabilities"] and body["capabilities"] == sorted(body["capabilities"])


def test_is_superuser_adds_no_capabilities(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP, is_superuser=True, is_staff=True)
    body = signed_in(user, settings).get(ME).json()
    assert body["capabilities"] == sorted(ROLE_CAPABILITIES[ROLE_SALES_FOLLOW_UP])


def test_a_user_with_no_role_has_no_capabilities(make_user, settings):
    body = signed_in(make_user(), settings).get(ME).json()
    assert (
        body["roles"] == []
        and body["capabilities"] == []
        and body["mfa"] == {"required": False, "enrolled": False}
    )


@pytest.mark.parametrize(
    ("role", "device", "expected"),
    [
        (ROLE_SALES_FOLLOW_UP, False, {"required": False, "enrolled": False}),
        (ROLE_CAMPAIGN_MANAGER, False, {"required": True, "enrolled": False}),
        (ROLE_ADMIN, True, {"required": True, "enrolled": True}),
        (ROLE_SALES_FOLLOW_UP, True, {"required": False, "enrolled": True}),
    ],
)
def test_mfa_state(role, device, expected, make_user, settings):
    user = make_user(role)
    if device:
        make_device(user)
    assert signed_in(user, settings).get(ME).json()["mfa"] == expected


def test_an_unconfirmed_device_is_not_enrolled(make_user, settings):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    make_device(user, confirmed=False)
    assert signed_in(user, settings).get(ME).json()["mfa"]["enrolled"] is False


def test_session_expiries_are_access_expiry_and_the_absolute_cap(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    with freeze_time("2026-10-11 12:00:00"):
        body = signed_in(user, settings).get(ME).json()
    start = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
    assert (parse(body["session"]["access_expires_at"]) - start).total_seconds() == settings.SIMPLE_JWT[
        "ACCESS_TOKEN_LIFETIME"
    ].total_seconds()
    assert (parse(body["session"]["absolute_expires_at"]) - start).total_seconds() == (
        settings.JWT_SESSION_ABSOLUTE_MAX_SECONDS
    )


def test_absolute_expiry_does_not_move_when_the_session_is_rotated(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    with freeze_time("2026-10-11 12:00:00") as clock:
        first = tokens.issue_tokens(user)
        clock.tick(7200)
        second = tokens.rotate_tokens(first.refresh)
        client = browser()
        client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = second.access
        body = client.get(ME).json()
    assert parse(body["session"]["absolute_expires_at"]) == datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    assert parse(body["session"]["access_expires_at"]) == datetime(2026, 10, 11, 14, 15, 0, tzinfo=UTC)


# --- who is refused ------------------------------------------------------------------------------------


def test_anonymous_is_the_uniform_401(settings):
    response = browser().get(ME)
    assert response.status_code == 401 and response.json() == UNIFORM_401
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("change", ["deactivated", "epoch", "deleted"])
def test_stale_users_are_refused(change, make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    client = signed_in(user, settings)
    if change == "deactivated":
        User.objects.filter(pk=user.pk).update(is_active=False)
    elif change == "epoch":
        user.bump_auth_epoch()
    else:
        User.objects.filter(pk=user.pk).delete()
    response = client.get(ME)
    assert response.status_code == 401 and response.json() == UNIFORM_401


def test_an_expired_access_token_is_refused(make_user, settings):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    with freeze_time("2026-10-11 12:00:00") as clock:
        client = signed_in(user, settings)
        clock.tick(901)
        response = client.get(ME)
    assert response.status_code == 401 and response.json() == UNIFORM_401


@pytest.mark.parametrize("junk", ["garbage", "a.b.c", "A" * 5000])
def test_a_bad_cookie_is_refused(junk, settings):
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = junk
    response = client.get(ME)
    assert response.status_code == 401 and response.json() == UNIFORM_401


def test_a_refresh_token_in_the_access_cookie_is_refused(make_user, settings):
    client = browser()
    client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = tokens.issue_tokens(make_user(ROLE_ADMIN)).refresh
    assert client.get(ME).status_code == 401


def test_the_restricted_enrolment_credential_is_403_and_never_reveals_the_profile(make_user, settings):
    user = make_user(ROLE_CAMPAIGN_MANAGER)  # needs MFA, none enrolled: the state that issues the credential
    response = browser().get(ME, HTTP_AUTHORIZATION=f"MfaEnroll {mfa.issue_enrollment_token(user)}")
    assert response.status_code == 403 and response.json() == FORBIDDEN_403
    assert user.email not in response.content.decode()


def test_an_invalid_enrolment_credential_is_the_uniform_401(settings):
    response = browser().get(ME, HTTP_AUTHORIZATION="MfaEnroll not-a-token")
    assert response.status_code == 401 and response.json() == UNIFORM_401


@pytest.mark.parametrize(
    "principal",
    [
        SimpleNamespace(is_authenticated=True),  # e.g. an API client: authenticated, but not a person
        SimpleNamespace(is_authenticated=True, has_capability=lambda name: True),
    ],
)
def test_non_human_principals_are_refused_by_the_permission(principal):
    request = APIRequestFactory().get(ME)
    request.user, request.auth = principal, SimpleNamespace(restricted=False)
    assert IsHumanSession().has_permission(request, None) is False


def test_the_permission_fails_closed_when_the_credential_has_no_restricted_flag(make_user):
    request = APIRequestFactory().get(ME)
    request.user, request.auth = make_user(ROLE_ADMIN), object()
    assert IsHumanSession().has_permission(request, None) is False


def test_only_get_is_allowed(make_user, settings):
    client = signed_in(make_user(ROLE_ADMIN), settings)
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)(ME)
        assert response.status_code in (403, 405)
        assert response.status_code != 200


# --- throttling, audit, logging ----------------------------------------------------------------------


def test_me_uses_the_api_user_scope_not_the_login_scope(make_user, settings, monkeypatch):
    monkeypatch.setitem(ApiUserThrottle.THROTTLE_RATES, "api-user", "2/min")
    monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "1000/min")
    client = signed_in(make_user(ROLE_SALES_FOLLOW_UP), settings)
    assert client.get(ME).status_code == 200 and client.get(ME).status_code == 200
    blocked = client.get(ME)
    assert blocked.status_code == 429 and int(blocked["Retry-After"]) > 0
    assert blocked.json() == {"code": "throttled", "message": "Too many requests."}


def test_the_api_user_bucket_is_per_user(make_user, settings, monkeypatch):
    monkeypatch.setitem(ApiUserThrottle.THROTTLE_RATES, "api-user", "1/min")
    first, second = signed_in(make_user(ROLE_ADMIN), settings), signed_in(make_user(ROLE_ADMIN), settings)
    assert first.get(ME).status_code == 200 and first.get(ME).status_code == 429
    assert second.get(ME).status_code == 200  # another user is unaffected


def test_reading_the_profile_writes_no_audit_event(make_user, settings):
    client = signed_in(make_user(ROLE_ADMIN), settings)
    before = AuditEvent.objects.count()
    assert client.get(ME).status_code == 200
    assert AuditEvent.objects.count() == before


def test_the_log_line_has_the_user_id_and_no_pii(make_user, settings, caplog):
    user = make_user(ROLE_SALES_FOLLOW_UP, full_name="Pat Private")
    with caplog.at_level("INFO", logger="apps.accounts.views"):
        signed_in(user, settings).get(ME)
    record = next(r for r in caplog.records if r.getMessage() == "identity read")
    assert record.user_id == str(user.pk)
    assert user.email not in caplog.text and "Pat Private" not in caplog.text
