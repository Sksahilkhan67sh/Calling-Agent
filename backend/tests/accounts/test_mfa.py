"""TOTP MFA: RFC 6238 vectors, window, replay, encrypted seeds, enrolment (P2-07)."""

import base64
import hashlib
import json
import logging
import uuid
from urllib.parse import parse_qs, unquote, urlparse

import pyotp
import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.accounts import mfa
from apps.accounts.models import MfaDevice, User
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER
from apps.audit import actions
from apps.audit.models import AuditEvent

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

NOW = 1_800_000_015.0  # mid-step, so +/- 1 step are comfortably inside the window
STEP = mfa.current_step(NOW)


def make_device(user: User, *, confirmed: bool = True, last_used: int = 0) -> tuple[MfaDevice, str]:
    seed = pyotp.random_base32()
    device_id = uuid.uuid4()
    device = MfaDevice.objects.create(
        id=device_id,
        user=user,
        secret_encrypted=mfa._cipher().encrypt(seed, context=mfa._context(device_id)),
        confirmed_at=timezone.now() if confirmed else None,
        last_used_step=last_used,
    )
    return device, seed


def failures(user: User) -> list[str]:
    events = AuditEvent.objects.filter(action=actions.AUTH_MFA_FAILED, object_id=str(user.pk))
    return [e.metadata["reason"] for e in events.order_by("occurred_at")]


@pytest.fixture
def manager(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


# --- RFC 6238 ----------------------------------------------------------------------------------------

RFC_SEED = base64.b32encode(
    b"12345678901234567890"
).decode()  # the RFC 6238 SHA-1 test seed, built at runtime
# (unix time, 8-digit code from RFC 6238 Appendix B). Six digits are the last six of the eight.
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize(("unix_time", "eight_digits"), RFC_VECTORS)
def test_rfc6238_sha1_vectors(unix_time, eight_digits):
    assert pyotp.TOTP(RFC_SEED, digits=8, digest=hashlib.sha1).at(unix_time) == eight_digits
    assert mfa.compute_code(RFC_SEED, unix_time // 30) == eight_digits[-6:]  # our 6-digit configuration


def test_totp_parameters_are_the_authenticator_app_compatible_ones(settings):
    assert (settings.MFA_TOTP_ALGORITHM, settings.MFA_TOTP_DIGITS, settings.MFA_TOTP_PERIOD_SECONDS) == (
        "SHA1",
        6,
        30,
    )


# --- window, malformed input -------------------------------------------------------------------------


@pytest.mark.parametrize(("offset", "accepted"), [(-2, False), (-1, True), (0, True), (1, True), (2, False)])
def test_window_edges(offset, accepted, manager):
    _, seed = make_device(manager)
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP + offset), now=NOW) is accepted


def test_wrong_code_is_rejected_and_audited(manager):
    _, seed = make_device(manager)
    good = mfa.compute_code(seed, STEP)
    wrong = f"{(int(good) + 1) % 1_000_000:06d}"
    assert mfa.verify_login_code(manager, wrong, now=NOW) is False
    assert failures(manager) == ["invalid"]
    event = AuditEvent.objects.get(action=actions.AUTH_MFA_FAILED)
    assert event.outcome == "failure" and wrong not in json.dumps(event.metadata)  # the guess is not recorded


@pytest.mark.parametrize(
    "code",
    [
        "",
        "12345",
        "1234567",
        "abcdef",
        " 123456",
        "123456 ",
        "123456\n",
        "١٢٣٤٥٦",
        "12 456",
        "1e5555",
        "0x1234",
    ],
)
def test_malformed_codes_are_rejected_without_touching_the_device(code, manager):
    device, _ = make_device(manager)
    assert mfa.verify_login_code(manager, code, now=NOW) is False
    assert failures(manager) == ["malformed"]
    device.refresh_from_db()
    assert device.last_used_step == 0


def test_user_without_a_device_fails(manager):
    assert mfa.verify_login_code(manager, "123456", now=NOW) is False
    assert failures(manager) == ["no_device"]


def test_disabled_or_unconfirmed_devices_do_not_verify(manager):
    pending, seed = make_device(manager, confirmed=False)
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP), now=NOW) is False
    pending.confirmed_at, pending.disabled_at = timezone.now(), timezone.now()
    pending.save()
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP), now=NOW) is False


# --- replay ------------------------------------------------------------------------------------------


def test_a_code_cannot_be_used_twice(manager):
    _, seed = make_device(manager)
    code = mfa.compute_code(seed, STEP)
    assert mfa.verify_login_code(manager, code, now=NOW) is True
    assert mfa.verify_login_code(manager, code, now=NOW) is False
    assert failures(manager) == ["replay"]


def test_older_steps_are_refused_once_a_newer_one_was_used(manager):
    _, seed = make_device(manager)
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP + 1), now=NOW) is True
    assert (
        mfa.verify_login_code(manager, mfa.compute_code(seed, STEP), now=NOW) is False
    )  # still in the window
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP - 1), now=NOW) is False
    assert failures(manager) == ["replay", "replay"]


def test_the_next_step_works_after_a_use(manager):
    _, seed = make_device(manager)
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP), now=NOW) is True
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP + 1), now=NOW + 30) is True


def test_a_failed_attempt_does_not_advance_the_replay_marker(manager):
    device, seed = make_device(manager)
    mfa.verify_login_code(manager, "000000", now=NOW)
    device.refresh_from_db()
    assert device.last_used_step == 0
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP), now=NOW) is True


def test_codes_of_one_user_do_not_work_for_another(manager, make_user):
    other = make_user(ROLE_CAMPAIGN_MANAGER)
    _, seed = make_device(manager)
    make_device(other)
    assert mfa.verify_login_code(other, mfa.compute_code(seed, STEP), now=NOW) is False


# --- encrypted at rest -------------------------------------------------------------------------------


def test_the_seed_is_never_stored_in_plaintext(manager):
    enrollment = mfa.begin_enrollment(manager)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT secret_encrypted FROM accounts_mfadevice WHERE id = %s", [enrollment.device_id]
        )
        raw = cursor.fetchone()[0]
        cursor.execute("SELECT t::text FROM accounts_mfadevice t WHERE id = %s", [enrollment.device_id])
        whole_row = cursor.fetchone()[0]
    assert raw.startswith("v1:") and enrollment.secret not in raw
    assert enrollment.secret not in whole_row and enrollment.secret.lower() not in whole_row.lower()


def test_ciphertext_is_bound_to_its_own_row(manager, make_user):
    other = make_user(ROLE_CAMPAIGN_MANAGER)
    mine, my_seed = make_device(manager)
    theirs, _ = make_device(other)
    # An attacker with database write access copies their own seed's ciphertext onto the victim's row.
    MfaDevice.objects.filter(pk=theirs.pk).update(secret_encrypted=mine.secret_encrypted)
    assert mfa.verify_login_code(other, mfa.compute_code(my_seed, STEP), now=NOW) is False
    assert failures(other) == ["seed_unreadable"]


def test_unreadable_seed_fails_closed_and_logs_without_secrets(manager, caplog):
    device, _ = make_device(manager)
    MfaDevice.objects.filter(pk=device.pk).update(secret_encrypted="v1:nokey:AAAA:BBBB")
    with caplog.at_level(logging.ERROR):
        assert mfa.verify_login_code(manager, "123456", now=NOW) is False
    record = next(r for r in caplog.records if r.getMessage() == "mfa seed could not be decrypted")
    assert record.device_id == str(device.pk)
    assert "v1:nokey" not in caplog.text and "v1:nokey" not in str(record.__dict__)


def test_key_rotation_reseals_the_seed_on_next_successful_use(manager, settings):
    device, seed = make_device(manager)
    settings.FIELD_ENCRYPTION_KEYS = [("rot2", b"R" * 32), *settings.FIELD_ENCRYPTION_KEYS]
    assert mfa.verify_login_code(manager, mfa.compute_code(seed, STEP), now=NOW) is True
    device.refresh_from_db()
    assert device.secret_encrypted.startswith("v1:rot2:")
    assert (
        mfa.verify_login_code(manager, mfa.compute_code(seed, STEP + 1), now=NOW + 30) is True
    )  # still readable


# --- enrolment ---------------------------------------------------------------------------------------


def test_begin_returns_the_secret_and_uri_once_and_hides_them_from_repr(manager):
    enrollment = mfa.begin_enrollment(manager)
    assert len(enrollment.secret) == 32 and pyotp.TOTP(enrollment.secret).now()  # 160-bit base32
    parsed = urlparse(enrollment.provisioning_uri)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp"
    assert query["secret"] == [enrollment.secret] and query["issuer"] == ["AI Calling Agent"]
    assert manager.email in unquote(parsed.path)
    assert enrollment.secret not in repr(enrollment) and "otpauth" not in repr(enrollment)


def test_seeds_are_unique_per_enrolment(manager, make_user):
    seeds = {mfa.begin_enrollment(u).secret for u in (manager, make_user(ROLE_ADMIN), make_user(ROLE_ADMIN))}
    assert len(seeds) == 3


def test_beginning_again_replaces_the_pending_device(manager):
    first = mfa.begin_enrollment(manager)
    second = mfa.begin_enrollment(manager)
    pending = MfaDevice.objects.filter(user=manager, confirmed_at__isnull=True, disabled_at__isnull=True)
    assert [d.pk for d in pending] == [second.device_id]
    assert MfaDevice.objects.get(pk=first.device_id).disabled_at is not None
    with pytest.raises(mfa.InvalidCode):  # the old secret no longer confirms anything
        mfa.confirm_enrollment(manager, mfa.compute_code(first.secret, STEP), now=NOW)


def test_cannot_begin_when_already_enrolled_or_inactive(manager):
    make_device(manager)
    with pytest.raises(mfa.AlreadyEnrolled):
        mfa.begin_enrollment(manager)
    manager.is_active = False
    manager.save()
    with pytest.raises(mfa.MfaError, match="not active"):
        mfa.begin_enrollment(manager)


def test_begin_is_audited_without_the_secret(manager):
    enrollment = mfa.begin_enrollment(manager)
    event = AuditEvent.objects.get(action=actions.AUTH_MFA_ENROLLMENT_STARTED)
    dump = json.dumps([event.before, event.after, event.metadata, event.object_id, event.actor_label])
    assert event.object_id == str(enrollment.device_id) and event.actor_label == manager.email
    assert enrollment.secret not in dump and "otpauth" not in dump


def test_confirm_activates_revokes_sessions_and_audits(manager):
    enrollment = mfa.begin_enrollment(manager)
    epoch = manager.auth_epoch
    mfa.confirm_enrollment(manager, mfa.compute_code(enrollment.secret, STEP), now=NOW)
    device = MfaDevice.objects.get(pk=enrollment.device_id)
    assert device.confirmed_at is not None and device.disabled_at is None and device.last_used_step == STEP
    assert User.objects.get(pk=manager.pk).auth_epoch == epoch + 1
    assert AuditEvent.objects.filter(action=actions.AUTH_MFA_ENROLLED, object_id=str(device.pk)).count() == 1


def test_the_enrolment_code_cannot_be_replayed_at_login(manager):
    enrollment = mfa.begin_enrollment(manager)
    code = mfa.compute_code(enrollment.secret, STEP)
    mfa.confirm_enrollment(manager, code, now=NOW)
    assert mfa.verify_login_code(manager, code, now=NOW) is False
    assert mfa.verify_login_code(manager, mfa.compute_code(enrollment.secret, STEP + 1), now=NOW + 30) is True


def test_wrong_code_keeps_enrolment_pending_and_is_audited(manager):
    enrollment = mfa.begin_enrollment(manager)
    with pytest.raises(mfa.InvalidCode):
        mfa.confirm_enrollment(manager, "000000", now=NOW)
    assert MfaDevice.objects.get(pk=enrollment.device_id).confirmed_at is None
    assert failures(manager) == ["invalid"] and User.objects.get(pk=manager.pk).auth_epoch == 0
    assert not AuditEvent.objects.filter(action=actions.AUTH_MFA_ENROLLED).exists()


def test_confirm_without_a_pending_device_or_twice(manager):
    with pytest.raises(mfa.NoPendingEnrollment):
        mfa.confirm_enrollment(manager, "123456", now=NOW)
    enrollment = mfa.begin_enrollment(manager)
    mfa.confirm_enrollment(manager, mfa.compute_code(enrollment.secret, STEP), now=NOW)
    with pytest.raises(mfa.NoPendingEnrollment):
        mfa.confirm_enrollment(manager, mfa.compute_code(enrollment.secret, STEP + 1), now=NOW + 30)


def test_the_database_allows_one_active_and_one_pending_device_per_user(manager):
    make_device(manager)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_device(manager)
    make_device(manager, confirmed=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_device(manager, confirmed=False)


def test_string_form_exposes_no_secret(manager):
    device, seed = make_device(manager)
    assert str(device) == f"MfaDevice {device.pk}" and seed not in str(device) + repr(device)
