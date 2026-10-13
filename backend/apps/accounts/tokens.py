"""Session tokens: issue, read, rotate (with reuse detection) and revoke (Django-Backend-Design §4.1).

Built on SimpleJWT's token classes and blacklist tables, but this module owns parsing and storage:
- Fixed HS256, ``iss``/``aud`` verified, access and refresh tokens are not interchangeable (``token_type``).
- Every token carries the user's ``auth_epoch``; once the epoch moves (password change, role change, MFA
  reset, deactivation, logout everywhere, reuse detection) all older tokens die at once.
- Refresh tokens rotate on every use. Only tokens recorded at issue time are accepted, and the table stores
  a SHA-256 digest, never the token: a read-only copy of the database yields no usable refresh token
  (stock SimpleJWT stores the full string).
- Presenting an already-rotated or logged-out refresh token is treated as theft: the user's epoch is bumped,
  which revokes every session, and the event is audited and logged.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenBackendError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from apps.accounts.models import User
from apps.audit import actions
from apps.audit.models import Outcome
from apps.audit.service import Actor, record

logger = logging.getLogger(__name__)

EPOCH_CLAIM = "auth_epoch"
ROLES_CLAIM = "roles"  # informational for clients; authorisation always reads the database
ACCESS = "access"
REFRESH = "refresh"
_MAX_TOKEN_LENGTH = 4096
_REQUIRED_NUMERIC = ("exp", "iat")


class InvalidToken(Exception):
    """Any problem with a presented token. Deliberately uniform: no reason is ever shown to the caller."""


class RefreshReuseDetected(InvalidToken):
    """A rotated or revoked refresh token was presented again; the user's sessions have been revoked."""


@dataclass(frozen=True)
class TokenPair:
    access: str = field(repr=False)
    refresh: str = field(repr=False)


@dataclass(frozen=True)
class Claims:
    user_id: uuid.UUID
    epoch: int
    jti: str
    expires_at: float


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _decode(raw: object, token_type: str) -> Claims:
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_TOKEN_LENGTH:
        raise InvalidToken
    try:
        # Verifies signature, algorithm, exp, iss, aud. (SimpleJWT mis-annotates the argument as Token.)
        payload: dict[str, Any] = token_backend.decode(raw, verify=True)  # type: ignore[arg-type]
    except (TokenBackendError, jwt.PyJWTError):
        raise InvalidToken from None
    if payload.get(api_settings.TOKEN_TYPE_CLAIM) != token_type:
        raise InvalidToken
    try:
        sub = payload[api_settings.USER_ID_CLAIM]
        epoch = payload[EPOCH_CLAIM]
        jti = payload[api_settings.JTI_CLAIM]
        times = [payload[name] for name in _REQUIRED_NUMERIC]
        if not isinstance(sub, str) or not isinstance(jti, str) or not jti or len(jti) > 64:
            raise InvalidToken
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            raise InvalidToken
        if any(isinstance(t, bool) or not isinstance(t, int | float) for t in times):
            raise InvalidToken
        return Claims(user_id=uuid.UUID(sub), epoch=epoch, jti=jti, expires_at=float(payload["exp"]))
    except (KeyError, ValueError):
        raise InvalidToken from None


def issue_tokens(user: User) -> TokenPair:
    """A new session: an access/refresh pair whose refresh token is recorded (as a digest) for rotation."""
    if not user.is_active:
        raise InvalidToken
    refresh = RefreshToken()
    refresh[api_settings.USER_ID_CLAIM] = str(user.pk)
    refresh[EPOCH_CLAIM] = user.auth_epoch
    refresh[ROLES_CLAIM] = sorted(user.role_names())
    raw_refresh = str(refresh)
    with transaction.atomic():
        OutstandingToken.objects.create(
            user=user,
            jti=refresh[api_settings.JTI_CLAIM],
            token=digest(raw_refresh),
            created_at=refresh.current_time,
            expires_at=datetime_from_epoch(refresh["exp"]),
        )
    return TokenPair(access=str(refresh.access_token), refresh=raw_refresh)


def read_access(raw: str) -> tuple[User, Claims]:
    """The user an access token authenticates, or ``InvalidToken``: unknown, inactive or stale epoch."""
    claims = _decode(raw, ACCESS)
    user = User.objects.filter(pk=claims.user_id).first()
    if user is None or not user.is_active or user.auth_epoch != claims.epoch:
        raise InvalidToken
    return user, claims


def rotate_tokens(raw: str) -> TokenPair:
    """Exchange a refresh token for a new pair. The old token is dead the moment this succeeds."""
    claims = _decode(raw, REFRESH)
    reused: User | None = None
    with transaction.atomic():
        outstanding = (
            OutstandingToken.objects.select_for_update(of=("self",))  # user is nullable: no lock on the join
            .select_related("user")
            .filter(jti=claims.jti)
            .first()
        )
        if outstanding is None or outstanding.user_id != claims.user_id:
            raise InvalidToken  # not a token we issued (or already housekept): fail closed
        if BlacklistedToken.objects.filter(token=outstanding).exists():
            reused = outstanding.user
        else:
            user = User.objects.select_for_update().filter(pk=claims.user_id, is_active=True).first()
            if user is None or user.auth_epoch != claims.epoch:
                raise InvalidToken
            BlacklistedToken.objects.create(token=outstanding)
            return issue_tokens(user)
    if reused is not None:  # always true here; committed before raising so the 401 cannot roll it back
        _handle_reuse(reused, claims.jti)
    raise RefreshReuseDetected


def _handle_reuse(user: User, jti: str) -> None:
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        locked.bump_auth_epoch()
        record(
            action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED,
            actor=Actor.user(locked),
            object_type="user",
            object_id=locked.pk,
            outcome=Outcome.FAILURE,
            metadata={"jti": jti},
        )
    logger.warning(
        "refresh token reuse detected; all sessions of the user revoked",
        extra={"user_id": str(locked.pk), "jti": jti},
    )


def revoke_refresh(raw: str) -> bool:
    """Blacklist a refresh token (logout). Idempotent; never reveals whether the token was valid."""
    try:
        claims = _decode(raw, REFRESH)
    except InvalidToken:
        return False
    with transaction.atomic():
        outstanding = OutstandingToken.objects.select_for_update().filter(jti=claims.jti).first()
        if outstanding is None or outstanding.user_id != claims.user_id:
            return False
        BlacklistedToken.objects.get_or_create(token=outstanding)
    return True
