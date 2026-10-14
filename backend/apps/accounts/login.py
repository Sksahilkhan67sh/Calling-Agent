"""Password check with equalised work and no user enumeration (Security-Architecture §2, surface 1).

Unknown, inactive and unusable-password accounts all perform one real password verification (against a
dummy hash made with the current preferred hasher), so the response time does not reveal which case it was.
A transparent hash upgrade is *not* a credential change and must not sign the user out, so it is written
without going through ``User.save()`` (which treats a changed password as a revocation trigger).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from functools import cache

from django.contrib.auth.hashers import is_password_usable, make_password, verify_password
from django.db.models.functions import Lower

from apps.accounts.models import User

UNKNOWN_USER = "unknown_user"
BAD_PASSWORD = "bad_password"  # noqa: S105 - an audit reason label, not a credential
INACTIVE = "inactive"
UNUSABLE_PASSWORD = "unusable_password"  # noqa: S105


@dataclass(frozen=True)
class CredentialCheck:
    user: User | None  # set only when the credentials are good and the account is active
    reason: str  # "" on success; an internal label for the audit trail, never shown to the caller
    target: User | None  # the account the attempt was aimed at, when one exists


@cache
def _dummy_hash() -> str:
    return make_password(secrets.token_urlsafe(16))


def _spend_the_same_effort(password: str) -> None:
    verify_password(password, _dummy_hash())


def check_credentials(email: str, password: str) -> CredentialCheck:
    user = User.objects.annotate(email_lower=Lower("email")).filter(email_lower=email.lower()).first()
    if user is None:
        _spend_the_same_effort(password)
        return CredentialCheck(None, UNKNOWN_USER, None)
    if not is_password_usable(user.password):
        _spend_the_same_effort(password)
        return CredentialCheck(None, UNUSABLE_PASSWORD, user)
    correct, must_update = verify_password(password, user.password)
    if not correct:
        return CredentialCheck(None, BAD_PASSWORD, user)
    if must_update:  # a stronger hasher or parameters are now preferred: re-hash while we hold the password
        User.objects.filter(pk=user.pk).update(password=make_password(password))
    if not user.is_active:
        return CredentialCheck(None, INACTIVE, user)
    return CredentialCheck(user, "", user)
