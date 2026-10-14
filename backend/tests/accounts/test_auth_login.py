"""POST /v1/auth/token: uniform failures, MFA step, equalised work, audit, throttling (P2-09)."""

import json
import logging
from unittest import mock

import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import caches

from apps.accounts import login as login_module
from apps.accounts.models import User
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.audit import actions
from apps.audit.models import AuditEvent
from apps.core.throttles import LoginThrottle
from tests.accounts.conftest import PASSWORD
from tests.accounts.helpers import browser, login, totp
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
def sales(make_user) -> User:
    return make_user(ROLE_SALES_FOLLOW_UP)


@pytest.fixture
def mfa_user(make_user):
    user = make_user(ROLE_CAMPAIGN_MANAGER)
    _, seed = make_device(user)
    return user, seed


# --- success -----------------------------------------------------------------------------------------


def test_password_login_sets_cookies_csrf_and_a_minimal_body(sales, settings):
    client = browser()
    response = login(client, sales.email)
    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "mfa_enrollment_required": False,
    }  # no tokens in the body
    for name in (
        settings.AUTH_ACCESS_COOKIE_NAME,
        settings.AUTH_REFRESH_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
    ):
        assert client.cookies[name].value
    assert response["Cache-Control"] == "no-store" and response["Pragma"] == "no-cache"
    event = AuditEvent.objects.get(action=actions.AUTH_LOGIN_SUCCESS)
    assert event.actor_label == sales.email and event.metadata == {"mfa": False}


def test_the_access_cookie_from_login_authenticates_later_requests(make_user, settings):
    manager = make_user(ROLE_CAMPAIGN_MANAGER)
    _, seed = make_device(manager)
    client = browser()
    assert login(client, manager.email, code=totp(seed)).status_code == 200
    whoami = client.get("/whoami/")
    assert (
        whoami.status_code == 200
        and whoami.json()["user"] == str(manager.pk)
        and whoami.json()["via"] == "cookie"
    )
    assert User.objects.get(pk=manager.pk).auth_epoch == 0  # login does not revoke anything


def test_each_login_starts_an_independent_session_with_a_fresh_csrf_token(sales, settings):
    first, second = browser(), browser()
    login(first, sales.email)
    login(second, sales.email)
    assert first.cookies[settings.CSRF_COOKIE_NAME].value != second.cookies[settings.CSRF_COOKIE_NAME].value
    assert (
        first.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
        != second.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    )


def test_email_is_matched_case_insensitively_and_trimmed(sales):
    for variant in (sales.email.upper(), sales.email.title(), f"  {sales.email}  "):
        assert login(browser(), variant).status_code == 200, variant


def test_lookalike_unicode_emails_are_not_normalised_into_a_match(sales):
    fullwidth = sales.email.replace("u", "\uff55")  # fullwidth 'u'
    assert login(browser(), fullwidth).status_code == 401


def test_tokens_are_in_the_body_only_in_body_mode(sales, settings):
    assert "access" not in login(browser(), sales.email).json()
    settings.AUTH_TOKENS_IN_BODY = True
    body = login(browser(), sales.email).json()
    assert body["authenticated"] is True and body["access"] and body["refresh"]


# --- MFA ---------------------------------------------------------------------------------------------


def test_mfa_user_needs_a_valid_code(mfa_user):
    user, seed = mfa_user
    assert login(browser(), user.email).status_code == 401  # no code
    assert login(browser(), user.email, code="000000").status_code == 401  # wrong code
    assert login(browser(), user.email, code=totp(seed)).status_code == 200


def test_mfa_code_is_not_checked_when_the_password_is_wrong(mfa_user):
    user, seed = mfa_user
    code = totp(seed)
    assert login(browser(), user.email, password="x" * 14, code=code).status_code == 401
    assert (
        login(browser(), user.email, code=code).status_code == 200
    )  # the code was not burned by the attempt


def test_a_used_code_cannot_log_in_again(mfa_user):
    user, seed = mfa_user
    code = totp(seed)
    assert login(browser(), user.email, code=code).status_code == 200
    assert login(browser(), user.email, code=code).status_code == 401  # replay
    assert login(browser(), user.email, code=totp(seed, ahead=1)).status_code == 200  # the next step is fine


def test_mfa_failures_are_audited_with_internal_reasons_only(mfa_user):
    user, _ = mfa_user
    login(browser(), user.email)
    login(browser(), user.email, code="000000")
    reasons = [
        e.metadata["reason"]
        for e in AuditEvent.objects.filter(action=actions.AUTH_LOGIN_FAILURE).order_by("occurred_at")
    ]
    assert reasons == ["mfa_missing", "mfa_invalid"]
    assert (
        AuditEvent.objects.filter(action=actions.AUTH_MFA_FAILED).count() == 1
    )  # the wrong code; a missing one is not a guess


def test_non_mfa_roles_log_in_with_a_password_alone(sales):
    assert login(browser(), sales.email).status_code == 200


# --- no enumeration ----------------------------------------------------------------------------------


def failure_variants(make_user, mfa_user):
    inactive = make_user(ROLE_SALES_FOLLOW_UP)
    User.objects.filter(pk=inactive.pk).update(is_active=False)
    unusable = make_user(ROLE_SALES_FOLLOW_UP)
    User.objects.filter(pk=unusable.pk).update(password="!" + "x" * 30)
    known = make_user(ROLE_SALES_FOLLOW_UP)
    user, _ = mfa_user
    return {
        "unknown_user": ("nobody@example.com", PASSWORD, None),
        "wrong_password": (known.email, "not-the-password-1", None),
        "inactive_but_correct_password": (inactive.email, PASSWORD, None),
        "unusable_password": (unusable.email, PASSWORD, None),
        "mfa_missing": (user.email, PASSWORD, None),
        "mfa_wrong": (user.email, PASSWORD, "000000"),
    }


def test_every_failure_is_the_same_response(make_user, mfa_user, monkeypatch):
    monkeypatch.setitem(
        LoginThrottle.THROTTLE_RATES, "login", "100/min"
    )  # six attempts: stay under the limiter
    seen = set()
    for email, password, code in failure_variants(make_user, mfa_user).values():
        response = login(browser(), email, password, code)
        assert response.status_code == 401
        seen.add(
            (
                response.content,
                response["Content-Type"],
                response["Cache-Control"],
                response.has_header("Set-Cookie"),
            )
        )
    assert seen == {
        (
            b'{"code":"invalid_credentials","message":"Invalid credentials."}',
            "application/json",
            "no-store",
            False,
        )
    }


@pytest.mark.parametrize(
    "case", ["unknown_user", "wrong_password", "inactive_but_correct_password", "unusable_password"]
)
def test_every_failure_path_performs_exactly_one_password_verification(case, make_user, mfa_user):
    """Deterministic proof of equalised work: the same single hash verification whichever way it fails."""
    email, password, _ = failure_variants(make_user, mfa_user)[case]
    with mock.patch.object(login_module, "verify_password", wraps=login_module.verify_password) as spy:
        login_module.check_credentials(email, password)
    assert spy.call_count == 1


@pytest.mark.timing
def test_unknown_user_and_wrong_password_take_comparable_time_under_argon2(settings, make_user):
    """Statistical check with the production hasher: medians over many samples, generous bound (0.5x-2x).

    The deterministic test above is the real guarantee; this one would catch a regression that skips the hash
    for unknown users. Median-of-15 with a 4x window keeps it stable on noisy CI runners."""
    import time

    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
    login_module._dummy_hash.cache_clear()
    user = make_user(ROLE_SALES_FOLLOW_UP)
    User.objects.filter(pk=user.pk).update(password=make_password(PASSWORD))

    def median_seconds(email: str) -> float:
        samples = []
        for _ in range(15):
            start = time.perf_counter()
            login_module.check_credentials(email, "wrong-password-12345")
            samples.append(time.perf_counter() - start)
        return sorted(samples)[len(samples) // 2]

    login_module.check_credentials("warmup@example.com", "x")  # builds the dummy hash outside the timing
    unknown, wrong = median_seconds("nobody@example.com"), median_seconds(user.email)
    assert 0.5 <= unknown / wrong <= 2.0, (unknown, wrong)
    login_module._dummy_hash.cache_clear()


def test_hash_upgrade_does_not_sign_the_user_out(sales, settings):
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",  # preferred
        "django.contrib.auth.hashers.MD5PasswordHasher",  # legacy
    ]
    User.objects.filter(pk=sales.pk).update(password=make_password(PASSWORD, hasher="md5"))
    before = User.objects.get(pk=sales.pk)
    assert before.password.startswith("md5$")
    assert login(browser(), sales.email).status_code == 200
    after = User.objects.get(pk=sales.pk)
    assert after.password.startswith("pbkdf2_sha256$")  # re-hashed with the preferred hasher
    assert after.auth_epoch == before.auth_epoch and after.password_changed_at == before.password_changed_at


# --- audit -------------------------------------------------------------------------------------------


def test_failures_are_audited_with_reasons_targets_and_safe_labels(make_user):
    known = make_user(ROLE_SALES_FOLLOW_UP)
    login(browser(), "nobody@example.com")
    login(browser(), known.email, password="wrong-password-12345")
    unknown, wrong = AuditEvent.objects.filter(action=actions.AUTH_LOGIN_FAILURE).order_by("occurred_at")
    assert (unknown.metadata["reason"], unknown.object_id, unknown.actor_label) == (
        "unknown_user",
        "",
        "nobody@example.com",
    )
    assert (wrong.metadata["reason"], wrong.object_id) == ("bad_password", str(known.pk))
    assert unknown.outcome == wrong.outcome == "failure" and unknown.actor_type == "anonymous"


def test_a_password_typed_into_the_email_field_is_never_stored(sales):
    typed = "My$ecret-Passw0rd-Not-An-Email"
    assert login(browser(), typed).status_code == 401
    event = AuditEvent.objects.get(action=actions.AUTH_LOGIN_FAILURE)
    assert event.actor_label == "" and typed not in json.dumps([event.metadata, event.actor_label])


def test_a_failed_audit_write_means_no_session(sales, settings):
    from apps.audit.service import AuditError

    client = browser()
    with mock.patch("apps.accounts.views.record", side_effect=AuditError("down")):
        response = login(client, sales.email)
    assert response.status_code == 500 and not response.cookies
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    assert not OutstandingToken.objects.exists()  # the rolled-back transaction left no issued token behind


# --- throttle ----------------------------------------------------------------------------------------


def test_login_is_rate_limited_per_client_with_retry_after(sales, monkeypatch):
    monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "3/min")
    statuses = [login(browser(), "nobody@example.com").status_code for _ in range(3)]
    blocked = login(browser(), sales.email)  # even correct credentials are refused once throttled
    assert statuses == [401, 401, 401] and blocked.status_code == 429
    assert int(blocked["Retry-After"]) > 0 and blocked.json() == {
        "code": "throttled",
        "message": "Too many requests.",
    }
    assert blocked["Cache-Control"] == "no-store"


def test_throttled_requests_do_not_reach_the_credential_check(monkeypatch):
    monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "1/min")
    login(browser(), "nobody@example.com")
    with mock.patch.object(login_module, "verify_password") as spy:
        assert login(browser(), "nobody@example.com").status_code == 429
    spy.assert_not_called()


# --- logging -----------------------------------------------------------------------------------------


def test_no_credential_ever_reaches_the_logs(mfa_user, caplog):
    user, seed = mfa_user
    code, wrong_password = totp(seed), "Wr0ng-passw0rd-for-log-test"
    client = browser()
    with caplog.at_level(logging.DEBUG):
        login(client, user.email, wrong_password, code)
        login(client, user.email, PASSWORD, "000000")
        login(client, user.email, PASSWORD, code)
    secrets_seen = [PASSWORD, wrong_password, code, "000000"] + [m.value for m in client.cookies.values()]
    log_text = caplog.text
    assert not [s for s in secrets_seen if s and s in log_text]
    assert ROLE_ADMIN  # (keeps the import used for readability of role names in this module)
