"""TOTP (RFC 6238) multi-factor authentication with encrypted seeds (Django-Backend-Design §4.1).

Why not ``django-otp``: its TOTP model stores the key in plaintext, so a database copy would hand an
attacker every user's second factor. Seeds here exist only as AES-GCM ciphertext (``FieldCipher``), bound
to their own row; the plaintext is returned once at enrolment and never stored, logged or audited.

Replay protection: ``last_used_step`` holds the highest accepted time step and a code for a step at or
below it is refused, so an observed code cannot be reused inside its validity window.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pyotp
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import MfaDevice, User
from apps.audit import actions
from apps.audit.models import Outcome
from apps.audit.service import Actor, record
from apps.core.crypto import DecryptionError, FieldCipher

logger = logging.getLogger(__name__)

SECRET_CONTEXT = "accounts_mfadevice.secret"  # noqa: S105 - encryption context label, not a secret
_CODE = re.compile(r"[0-9]{6}", re.ASCII)
_TOKEN_SALT = "accounts.mfa-enrollment"  # noqa: S105 - a signing salt, not a credential
_TOKEN_PURPOSE = "mfa-enroll"  # noqa: S105
_MAX_TOKEN_LENGTH = 1024


class MfaError(Exception):
    """Base class; messages are safe to show to the caller (never contain secrets)."""


class AlreadyEnrolled(MfaError):
    pass


class NoPendingEnrollment(MfaError):
    pass


class InvalidCode(MfaError):
    pass


class EnrollmentTokenInvalid(MfaError):
    pass


@dataclass(frozen=True)
class Enrollment:
    """Returned once by ``begin_enrollment``. ``repr`` hides the secret and URI."""

    device_id: uuid.UUID
    secret: str = field(repr=False)
    provisioning_uri: str = field(repr=False)


# --- TOTP maths --------------------------------------------------------------------------------------


def _totp(seed: str) -> pyotp.TOTP:
    return pyotp.TOTP(
        seed,
        digits=settings.MFA_TOTP_DIGITS,
        digest=hashlib.sha1,  # noqa: S324 - RFC 6238 default, the only algorithm authenticator apps all honour
        interval=settings.MFA_TOTP_PERIOD_SECONDS,
    )


def compute_code(seed: str, step: int) -> str:
    """The code for time step ``step`` (steps are ``unix_time // period``)."""
    return str(_totp(seed).at(step * settings.MFA_TOTP_PERIOD_SECONDS))


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // settings.MFA_TOTP_PERIOD_SECONDS)


def match_step(seed: str, code: str, *, now: float | None = None) -> int | None:
    """The newest step inside the +/- window whose code equals ``code``, else ``None``.

    Every step in the window is always evaluated and compared in constant time, so timing reveals
    neither which step matched nor how many digits were right.
    """
    centre, window = current_step(now), settings.MFA_TOTP_WINDOW_STEPS
    matched: int | None = None
    for step in range(centre - window, centre + window + 1):
        if hmac.compare_digest(compute_code(seed, step).encode(), code.encode()):
            matched = step
    return matched


# --- seed storage ------------------------------------------------------------------------------------


def _cipher() -> FieldCipher:
    return FieldCipher(settings.FIELD_ENCRYPTION_KEYS)


def _context(device_id: uuid.UUID) -> str:
    return f"{SECRET_CONTEXT}|{device_id}"


def _read_seed(device: MfaDevice) -> str | None:
    """Decrypt the seed; ``None`` (and an error log without secrets) if it cannot be read: fail closed."""
    cipher = _cipher()
    try:
        seed = cipher.decrypt(device.secret_encrypted, context=_context(device.pk))
    except DecryptionError:
        logger.error("mfa seed could not be decrypted", extra={"device_id": str(device.pk)})
        return None
    if cipher.needs_rotation(device.secret_encrypted):  # sealed with an older key: re-seal with the newest
        device.secret_encrypted = cipher.encrypt(seed, context=_context(device.pk))
        device.save(update_fields=["secret_encrypted"])
    return seed


# --- verification ------------------------------------------------------------------------------------


def _check_code(device: MfaDevice, code: str, *, now: float | None) -> tuple[int | None, str]:
    """(accepted step or None, failure reason). Caller holds a lock on ``device``."""
    if not _CODE.fullmatch(code):
        return None, "malformed"
    seed = _read_seed(device)
    if seed is None:
        return None, "seed_unreadable"
    step = match_step(seed, code, now=now)
    if step is None:
        return None, "invalid"
    if step <= device.last_used_step:
        return None, "replay"
    return step, ""


def _record_failure(user: User, actor: Actor, reason: str, device_id: uuid.UUID | None) -> None:
    with transaction.atomic():  # its own transaction: the failed attempt must stay on record
        record(
            action=actions.AUTH_MFA_FAILED,
            actor=actor,
            object_type="user",
            object_id=user.pk,
            outcome=Outcome.FAILURE,
            metadata={"reason": reason, "device_id": str(device_id) if device_id else ""},
        )


def verify_login_code(user: User, code: str, *, now: float | None = None) -> bool:
    """Check a TOTP code against the user's active device. Replay-protected; failures are audited."""
    actor = Actor.user(user)
    device_id: uuid.UUID | None = None
    reason = "no_device"
    with transaction.atomic():
        device = (
            MfaDevice.objects.select_for_update()
            .filter(user=user, confirmed_at__isnull=False, disabled_at__isnull=True)
            .first()
        )
        if device is not None:
            device_id = device.pk
            step, reason = _check_code(device, code, now=now)
            if step is not None:
                device.last_used_step = step
                device.save(update_fields=["last_used_step"])
                return True
    _record_failure(user, actor, reason, device_id)
    return False


# --- enrolment ---------------------------------------------------------------------------------------


def begin_enrollment(user: User, *, actor: Actor | None = None) -> Enrollment:
    """Create a pending device and return its secret and provisioning URI (shown once, never stored)."""
    if not user.is_active:
        raise MfaError("User is not active")
    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)  # serialise concurrent enrolments
        if user.has_active_mfa_device:
            raise AlreadyEnrolled("An authenticator is already enrolled; an administrator must reset it")
        MfaDevice.objects.filter(user=user, confirmed_at__isnull=True, disabled_at__isnull=True).update(
            disabled_at=timezone.now()
        )
        seed = pyotp.random_base32()  # 160 bits from the OS CSPRNG
        device_id = uuid.uuid4()
        MfaDevice.objects.create(
            id=device_id,
            user=user,
            secret_encrypted=_cipher().encrypt(seed, context=_context(device_id)),
        )
        record(
            action=actions.AUTH_MFA_ENROLLMENT_STARTED,
            actor=actor or Actor.user(user),
            object_type="mfa_device",
            object_id=device_id,
        )
    uri = _totp(seed).provisioning_uri(name=user.email, issuer_name=settings.MFA_ISSUER_NAME)
    return Enrollment(device_id=device_id, secret=seed, provisioning_uri=uri)


def confirm_enrollment(
    user: User, code: str, *, actor: Actor | None = None, now: float | None = None
) -> None:
    """Activate the pending device when ``code`` is valid. Revokes the user's other sessions."""
    actor = actor or Actor.user(user)
    reason, device_id = "", None
    with transaction.atomic():
        device = (
            MfaDevice.objects.select_for_update()
            .filter(user=user, confirmed_at__isnull=True, disabled_at__isnull=True)
            .first()
        )
        if device is None:
            raise NoPendingEnrollment("No enrolment is in progress")
        device_id = device.pk
        step, reason = _check_code(device, code, now=now)
        if step is not None:
            device.confirmed_at = timezone.now()
            device.last_used_step = step  # the enrolment code cannot be replayed at the next login
            device.save(update_fields=["confirmed_at", "last_used_step"])
            user.bump_auth_epoch()
            record(
                action=actions.AUTH_MFA_ENROLLED,
                actor=actor,
                object_type="mfa_device",
                object_id=device.pk,
            )
            return
    _record_failure(user, actor, reason, device_id)
    raise InvalidCode("The code is not valid")


def reset_mfa(user: User, *, actor: Actor) -> int:
    """Disable every device (lost phone) and revoke all sessions. Returns how many devices were disabled."""
    with transaction.atomic():
        disabled = MfaDevice.objects.filter(user=user, disabled_at__isnull=True).update(
            disabled_at=timezone.now()
        )
        user.bump_auth_epoch()
        record(
            action=actions.AUTH_MFA_RESET,
            actor=actor,
            object_type="user",
            object_id=user.pk,
            after={"devices_disabled": disabled},
        )
    return disabled


# --- restricted enrolment credential -----------------------------------------------------------------


def issue_enrollment_token(user: User) -> str:
    """A short-lived signed token that is good for the two enrolment endpoints and nothing else.

    It is not a JWT and uses its own signing salt, so no session authenticator can parse it; it embeds the
    user's ``auth_epoch``, so confirming enrolment (which bumps the epoch) or any revocation kills it.
    """
    payload = {"uid": str(user.pk), "epoch": user.auth_epoch, "purpose": _TOKEN_PURPOSE}
    return signing.dumps(payload, key=settings.JWT_SIGNING_KEY, salt=_TOKEN_SALT, compress=False)


def read_enrollment_token(token: str) -> User:
    """The user a valid enrolment token belongs to; ``EnrollmentTokenInvalid`` (uniform) otherwise."""
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        raise EnrollmentTokenInvalid("Invalid credentials")
    try:
        payload: Any = signing.loads(
            token,
            key=settings.JWT_SIGNING_KEY,
            salt=_TOKEN_SALT,
            max_age=settings.MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS,
        )
    except signing.BadSignature:  # includes SignatureExpired
        raise EnrollmentTokenInvalid("Invalid credentials") from None
    if not isinstance(payload, dict) or payload.get("purpose") != _TOKEN_PURPOSE:
        raise EnrollmentTokenInvalid("Invalid credentials")
    try:
        user = User.objects.filter(pk=uuid.UUID(str(payload.get("uid"))), is_active=True).first()
    except ValueError:
        user = None
    if user is None or user.auth_epoch != payload.get("epoch") or not user.must_enroll_mfa:
        raise EnrollmentTokenInvalid("Invalid credentials")
    return user
