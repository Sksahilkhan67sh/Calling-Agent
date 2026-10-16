"""MFA reset, the computed must_enroll flag, and the restricted enrolment credential (P2-07)."""

import json
import logging

import pyotp
import pytest
from django.core import signing
from freezegun import freeze_time
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts import mfa
from apps.accounts.models import MfaDevice, User
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.audit import actions
from apps.audit.models import AuditEvent
from apps.audit.service import Actor
from tests.accounts.test_mfa import NOW, STEP, make_device

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.urls("tests.testapp.urls")]


@pytest.fixture
def manager(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


def enroll(user: User) -> str:
    enrollment = mfa.begin_enrollment(user)
    mfa.confirm_enrollment(user, mfa.compute_code(enrollment.secret, STEP), now=NOW)
    return enrollment.secret


# --- must_enroll_mfa / reset -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role_names", "expected"),
    [
        ((ROLE_CAMPAIGN_MANAGER,), True),
        ((ROLE_ADMIN,), True),
        ((ROLE_SALES_FOLLOW_UP,), False),
        ((), False),
    ],
)
def test_must_enroll_follows_roles_until_a_device_is_active(role_names, expected, make_user):
    user = make_user(*role_names)
    assert user.must_enroll_mfa is expected
    if expected:
        enroll(user)
        assert user.must_enroll_mfa is False and user.has_active_mfa_device is True


def test_a_pending_device_does_not_count_as_enrolled(manager):
    mfa.begin_enrollment(manager)
    assert manager.must_enroll_mfa is True and manager.has_active_mfa_device is False


def test_reset_disables_devices_revokes_sessions_and_audits(manager):
    enroll(manager)
    epoch = User.objects.get(pk=manager.pk).auth_epoch
    admin_actor = Actor.system("system:cli:ops")
    assert mfa.reset_mfa(manager, actor=admin_actor) == 1
    fresh = User.objects.get(pk=manager.pk)
    assert fresh.auth_epoch == epoch + 1 and fresh.must_enroll_mfa is True
    assert not MfaDevice.objects.filter(user=manager, disabled_at__isnull=True).exists()
    event = AuditEvent.objects.get(action=actions.AUTH_MFA_RESET)
    assert event.actor_label == "system:cli:ops" and event.after == {"devices_disabled": 1}


def test_old_codes_stop_working_after_reset_and_re_enrolment_gets_a_new_seed(manager):
    old_seed = enroll(manager)
    mfa.reset_mfa(manager, actor=Actor.system("t"))
    assert mfa.verify_login_code(manager, mfa.compute_code(old_seed, STEP + 1), now=NOW + 30) is False
    again = mfa.begin_enrollment(manager)
    assert again.secret != old_seed


def test_reset_with_no_device_still_revokes_and_audits(manager):
    assert mfa.reset_mfa(manager, actor=Actor.system("t")) == 0
    assert User.objects.get(pk=manager.pk).auth_epoch == 1
    assert AuditEvent.objects.filter(action=actions.AUTH_MFA_RESET).count() == 1


# --- the token ---------------------------------------------------------------------------------------


def test_token_round_trip(manager):
    assert mfa.read_enrollment_token(mfa.issue_enrollment_token(manager)) == manager


def test_tampered_token_is_rejected(manager):
    token = mfa.issue_enrollment_token(manager)
    flipped = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(flipped)


@pytest.mark.parametrize("junk", ["", "x", "a:b:c", "A" * 2000, "not.a.token", "\x00", "..", "e30:1:zzz"])
def test_garbage_is_rejected_uniformly(junk):
    with pytest.raises(mfa.EnrollmentTokenInvalid, match="Invalid credentials"):
        mfa.read_enrollment_token(junk)


def test_token_expires_after_the_configured_lifetime(manager, settings):
    with freeze_time("2026-10-11 12:00:00") as clock:
        token = mfa.issue_enrollment_token(manager)
        clock.tick(settings.MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS - 1)
        assert mfa.read_enrollment_token(token) == manager
        clock.tick(2)
        with pytest.raises(mfa.EnrollmentTokenInvalid):
            mfa.read_enrollment_token(token)


def test_token_signed_for_another_purpose_or_with_another_key_is_rejected(manager, settings):
    payload = {"uid": str(manager.pk), "epoch": manager.auth_epoch, "purpose": "mfa-enroll"}
    for kwargs in (
        {"key": settings.JWT_SIGNING_KEY, "salt": "some.other.feature"},
        {"key": settings.SECRET_KEY, "salt": "accounts.mfa-enrollment"},
    ):
        with pytest.raises(mfa.EnrollmentTokenInvalid):
            mfa.read_enrollment_token(signing.dumps(payload, **kwargs))


@pytest.mark.parametrize(
    "payload",
    [
        {"uid": "not-a-uuid", "epoch": 0, "purpose": "mfa-enroll"},
        {"uid": "00000000-0000-0000-0000-000000000000", "epoch": 0, "purpose": "mfa-enroll"},
        {"epoch": 0, "purpose": "mfa-enroll"},
        ["a", "list"],
        "a string",
    ],
)
def test_validly_signed_but_wrong_content_is_rejected(payload, settings):
    token = signing.dumps(payload, key=settings.JWT_SIGNING_KEY, salt="accounts.mfa-enrollment")
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(token)


def test_wrong_purpose_claim_is_rejected(manager, settings):
    payload = {"uid": str(manager.pk), "epoch": manager.auth_epoch, "purpose": "something-else"}
    token = signing.dumps(payload, key=settings.JWT_SIGNING_KEY, salt="accounts.mfa-enrollment")
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(token)


def test_token_dies_when_the_session_epoch_moves(manager):
    token = mfa.issue_enrollment_token(manager)
    manager.bump_auth_epoch()
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(token)


def test_token_cannot_be_used_after_enrolment_is_confirmed(manager):
    token = mfa.issue_enrollment_token(manager)
    enrollment = mfa.begin_enrollment(manager)
    mfa.confirm_enrollment(manager, mfa.compute_code(enrollment.secret, STEP), now=NOW)
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(token)


def test_token_is_refused_for_inactive_users_and_for_users_who_need_no_enrolment(manager, make_user):
    token = mfa.issue_enrollment_token(manager)
    User.objects.filter(pk=manager.pk).update(is_active=False)  # isolate the is_active check from the epoch
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(token)
    sales = make_user(ROLE_SALES_FOLLOW_UP)
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(mfa.issue_enrollment_token(sales))
    enrolled = make_user(ROLE_ADMIN)
    stale = mfa.issue_enrollment_token(enrolled)
    make_device(enrolled)
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(stale)


def test_token_is_not_a_jwt_and_a_jwt_is_not_an_enrolment_token(manager):
    token = mfa.issue_enrollment_token(manager)
    with pytest.raises(TokenError):
        AccessToken(token)
    with pytest.raises(mfa.EnrollmentTokenInvalid):
        mfa.read_enrollment_token(str(RefreshToken.for_user(manager).access_token))


# --- over HTTP: the credential works for the enrolment endpoints and nowhere else ---------------------


def post_probe(client, header):
    return (
        client.post("/enroll-probe/", HTTP_AUTHORIZATION=header) if header else client.post("/enroll-probe/")
    )


def test_enrolment_endpoints_accept_the_credential(manager, api_as):
    token = mfa.issue_enrollment_token(manager)
    response = post_probe(api_as(None), f"MfaEnroll {token}")
    assert response.status_code == 200 and response.json() == {"user": str(manager.pk)}


def test_the_scheme_name_is_case_insensitive_but_other_schemes_are_ignored(manager, api_as):
    token = mfa.issue_enrollment_token(manager)
    assert post_probe(api_as(None), f"mfaenroll {token}").status_code == 200
    for header in (f"Bearer {token}", f"Token {token}", token, ""):
        response = post_probe(api_as(None), header)
        assert response.status_code == 401 and response["WWW-Authenticate"] == "MfaEnroll"


def test_failures_are_uniform_for_every_kind_of_bad_token(manager, api_as, settings):
    good = mfa.issue_enrollment_token(manager)
    manager.bump_auth_epoch()  # `good` is now revoked
    bodies = {
        json.dumps(post_probe(api_as(None), f"MfaEnroll {t}").json(), sort_keys=True)
        for t in (good, "garbage", good[:-3] + "xyz", "A" * 5000)
    }
    assert len(bodies) == 1 and "epoch" not in bodies.pop()


def test_normal_session_users_cannot_use_the_enrolment_endpoints(manager, api_as):
    response = api_as(manager).post("/enroll-probe/")
    assert response.status_code in (401, 403)


def test_the_credential_never_grants_role_capabilities(make_user, api_as):
    admin = make_user(ROLE_ADMIN)  # holds many capabilities, but is an enrolment-state login
    token = mfa.issue_enrollment_token(admin)
    client = api_as(None)
    # even a view that (wrongly) accepts the enrolment authenticator refuses it for capability checks
    response = client.get("/enroll-capability-probe/", HTTP_AUTHORIZATION=f"MfaEnroll {token}")
    assert response.status_code == 403 and "leaked" not in response.json()


def test_the_credential_is_not_accepted_by_ordinary_endpoints(manager, api_as):
    token = mfa.issue_enrollment_token(manager)
    for path in ("/things/", "/retry-policy/"):
        response = api_as(None).get(path, HTTP_AUTHORIZATION=f"MfaEnroll {token}")
        assert response.status_code in (401, 403)
    assert api_as(None).post(
        "/things/new/", {"title": "x"}, HTTP_AUTHORIZATION=f"MfaEnroll {token}"
    ).status_code in (
        401,
        403,
    )


def test_the_credential_stops_working_the_moment_enrolment_is_confirmed(manager, api_as):
    token = mfa.issue_enrollment_token(manager)
    enrollment = mfa.begin_enrollment(manager)
    assert post_probe(api_as(None), f"MfaEnroll {token}").status_code == 200
    mfa.confirm_enrollment(manager, mfa.compute_code(enrollment.secret, STEP), now=NOW)
    assert post_probe(api_as(None), f"MfaEnroll {token}").status_code == 401


# --- no secrets leak anywhere ------------------------------------------------------------------------


def test_no_seed_uri_or_code_reaches_logs_or_audit(manager, caplog):
    with caplog.at_level(logging.DEBUG):
        enrollment = mfa.begin_enrollment(manager)
        code = mfa.compute_code(enrollment.secret, STEP)
        with pytest.raises(mfa.InvalidCode):
            mfa.confirm_enrollment(manager, "000000", now=NOW)  # a failure path
        mfa.confirm_enrollment(manager, code, now=NOW)
        mfa.verify_login_code(manager, code, now=NOW)  # a replay failure
        mfa.verify_login_code(manager, mfa.compute_code(enrollment.secret, STEP + 1), now=NOW + 30)
        mfa.issue_enrollment_token(manager)
    everything = caplog.text + json.dumps(
        list(AuditEvent.objects.values("before", "after", "metadata", "object_id", "actor_label")),
        default=str,
    )
    assert enrollment.secret not in everything and "otpauth" not in everything
    assert code not in everything and "000000" not in everything


def test_pyotp_secrets_are_160_bits():
    assert len(pyotp.random_base32()) == 32  # 32 base32 characters = 160 bits
