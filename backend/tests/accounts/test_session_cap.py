"""Absolute session lifetime (R6, OQ2-01): ``sid`` / ``sat`` claims and the cap on refresh."""

import jwt
import pytest
from django.conf import settings
from freezegun import freeze_time

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.roles import ROLE_CAMPAIGN_MANAGER
from apps.audit import actions
from apps.audit.models import AuditEvent
from tests.accounts import forge

pytestmark = pytest.mark.django_db

CAP = 7 * 86400  # SESSION_ABSOLUTE_MAX_DAYS default
START = "2026-10-11 12:00:00"


@pytest.fixture
def user(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


def claims_of(raw: str) -> dict:
    return jwt.decode(raw, options={"verify_signature": False})


def test_the_cap_comes_from_the_setting():
    assert settings.JWT_SESSION_ABSOLUTE_MAX_SECONDS == CAP


def test_a_new_session_gets_a_session_id_and_start_in_both_tokens(user):
    with freeze_time(START):
        pair = tokens.issue_tokens(user)
        access, refresh = claims_of(pair.access), claims_of(pair.refresh)
        assert access["sid"] == refresh["sid"] and access["sat"] == refresh["sat"]
        assert len(refresh["sid"]) == 32 and refresh["sat"] == int(tokens.time.time())


def test_two_logins_are_two_sessions(user):
    assert (
        claims_of(tokens.issue_tokens(user).refresh)["sid"]
        != claims_of(tokens.issue_tokens(user).refresh)["sid"]
    )


def test_rotation_preserves_the_session_start_and_id(user):
    with freeze_time(START) as clock:
        first = tokens.issue_tokens(user)
        clock.tick(3600)
        second = tokens.rotate_tokens(first.refresh)
        before, after = claims_of(first.refresh), claims_of(second.refresh)
        assert after["sid"] == before["sid"] and after["sat"] == before["sat"]  # not extended by activity
        assert after["iat"] > before["iat"] and after["jti"] != before["jti"]
        assert claims_of(second.access)["sat"] == before["sat"]


def _rotate_every_12_hours_until(clock, pair, seconds_from_start: int):
    """Keep the session alive by rotating twice a day, as an active client would."""
    elapsed = 0
    while elapsed + 43200 <= seconds_from_start:
        clock.tick(43200)
        elapsed += 43200
        pair = tokens.rotate_tokens(pair.refresh)
    clock.tick(seconds_from_start - elapsed)
    return pair


def test_refresh_one_second_before_the_cap_succeeds(user):
    with freeze_time(START) as clock:
        pair = _rotate_every_12_hours_until(clock, tokens.issue_tokens(user), CAP - 1)
        assert tokens.rotate_tokens(pair.refresh)  # still inside the cap


def test_refresh_one_second_after_the_cap_is_rejected_however_active_the_user_was(user):
    with freeze_time(START) as clock:
        pair = _rotate_every_12_hours_until(clock, tokens.issue_tokens(user), CAP - 1)
        pair = tokens.rotate_tokens(pair.refresh)  # fresh refresh token issued 1 s before the cap
        clock.tick(2)
        with pytest.raises(tokens.SessionExpired):
            tokens.rotate_tokens(
                pair.refresh
            )  # the token itself is valid for another day; the session is not


def _pair_just_past_the_cap(clock, user):
    """A newest refresh token, 2 s past its session's cap: the token itself is still valid."""
    pair = _rotate_every_12_hours_until(clock, tokens.issue_tokens(user), CAP - 1)
    pair = tokens.rotate_tokens(pair.refresh)
    clock.tick(2)
    return pair


def test_an_expired_session_writes_one_audit_event_and_does_not_revoke_other_sessions(user):
    with freeze_time(START) as clock:
        tokens.issue_tokens(user)  # another session of the same user, started later in the same instant
        pair = _pair_just_past_the_cap(clock, user)
        epoch = User.objects.get(pk=user.pk).auth_epoch
        with pytest.raises(tokens.SessionExpired):
            tokens.rotate_tokens(pair.refresh)
    events = AuditEvent.objects.filter(action=actions.AUTH_SESSION_EXPIRED)
    assert events.count() == 1 and events.get().actor_id == user.pk
    assert User.objects.get(pk=user.pk).auth_epoch == epoch  # an expiry is not theft: no revoke-everything


def test_a_replayed_expired_token_is_not_treated_as_reuse(user):
    with freeze_time(START) as clock:
        pair = _pair_just_past_the_cap(clock, user)
        for _ in range(2):
            with pytest.raises(tokens.SessionExpired):
                tokens.rotate_tokens(pair.refresh)
    assert not AuditEvent.objects.filter(action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED).exists()
    assert (
        AuditEvent.objects.filter(action=actions.AUTH_SESSION_EXPIRED).count() == 2
    )  # one per rejected attempt


def test_an_expired_session_of_a_deleted_user_is_refused_without_an_audit_event(user):
    with freeze_time(START) as clock:
        pair = _pair_just_past_the_cap(clock, user)
        User.objects.filter(pk=user.pk).delete()
        with pytest.raises(tokens.SessionExpired):
            tokens.rotate_tokens(pair.refresh)
    assert not AuditEvent.objects.filter(action=actions.AUTH_SESSION_EXPIRED).exists()


def test_an_access_token_of_an_expired_session_is_rejected_too(user):
    now = int(tokens.time.time())
    ok = forge.sign(forge.payload(user, sat=now - CAP + 60))
    assert tokens.read_access(ok)[0] == user
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(forge.sign(forge.payload(user, sat=now - CAP - 60)))


@pytest.mark.parametrize("claim", ["sid", "sat"])
def test_tokens_without_the_session_claims_are_rejected(user, claim):
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(forge.sign(forge.payload(user, **{claim: ...})))


@pytest.mark.parametrize(
    "override",
    [
        {"sat": True},
        {"sat": -1},
        {"sat": "1760000000"},
        {"sat": None},
        {"sid": ""},
        {"sid": 12345},
        {"sid": "x" * 65},
    ],
)
def test_malformed_session_claims_are_rejected(user, override):
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(forge.sign(forge.payload(user, **override)))


@pytest.mark.parametrize("claim", ["sat", "sid"])
def test_tampering_with_the_session_claims_breaks_the_signature(user, claim):
    pair = tokens.issue_tokens(user)
    forged = claims_of(pair.refresh)
    forged[claim] = int(forged["sat"]) + 86400 if claim == "sat" else "f" * 32
    wrong_key = forge.sign(forged, key="a-different-signing-key-of-sufficient-length-0123456789")
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(wrong_key)
    # the same edit made to the payload segment of a genuine token is caught as well
    head, _, tail = pair.refresh.split(".")
    edited = forge.sign(forged, key="x" * 64).split(".")[1]
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(f"{head}.{edited}.{tail}")


def test_access_and_refresh_are_still_not_interchangeable_with_the_new_claims(user):
    pair = tokens.issue_tokens(user)
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(pair.refresh)
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(pair.access)
