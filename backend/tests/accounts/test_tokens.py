"""Token layer: claims, forgery resistance, rotation, reuse detection, digest-only storage (P2-08)."""

import json
import logging

import jwt
import pytest
from django.core.management import call_command
from django.db import connection
from freezegun import freeze_time
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts import tokens
from apps.accounts.models import User
from apps.accounts.roles import ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from apps.audit import actions
from apps.audit.models import AuditEvent
from tests.accounts import forge

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    # The HS512 forgery signs with the 54-byte test key, which PyJWT flags as short for SHA-512 only.
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),
]


@pytest.fixture
def user(make_user) -> User:
    return make_user(ROLE_CAMPAIGN_MANAGER)


def decoded(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


# --- issued tokens -----------------------------------------------------------------------------------


def test_issued_claims_and_lifetimes(user, settings):
    pair = tokens.issue_tokens(user)
    access, refresh = decoded(pair.access), decoded(pair.refresh)
    for token, kind in ((access, "access"), (refresh, "refresh")):
        assert token["token_type"] == kind and token["sub"] == str(user.pk) and token["auth_epoch"] == 0
        assert token["iss"] == settings.JWT_ISSUER and token["aud"] == settings.JWT_AUDIENCE
        assert token["roles"] == [ROLE_CAMPAIGN_MANAGER] and token["jti"] and token["iat"] and token["exp"]
    assert access["exp"] - access["iat"] == settings.JWT_ACCESS_LIFETIME_SECONDS == 900
    assert refresh["exp"] - refresh["iat"] == settings.JWT_REFRESH_LIFETIME_SECONDS
    assert access["jti"] != refresh["jti"]


def test_algorithm_is_fixed_to_hs256(user):
    assert jwt.get_unverified_header(tokens.issue_tokens(user).access)["alg"] == "HS256"


def test_no_email_or_password_material_in_tokens(user):
    pair = tokens.issue_tokens(user)
    for token in (pair.access, pair.refresh):
        assert user.email not in json.dumps(decoded(token)) and user.password not in json.dumps(
            decoded(token)
        )


def test_inactive_users_get_no_tokens(user):
    User.objects.filter(pk=user.pk).update(is_active=False)
    with pytest.raises(tokens.InvalidToken):
        tokens.issue_tokens(User.objects.get(pk=user.pk))


def test_token_pair_repr_hides_the_tokens(user):
    pair = tokens.issue_tokens(user)
    assert pair.access not in repr(pair) and pair.refresh not in repr(pair)


def test_only_a_digest_of_the_refresh_token_is_stored(user):
    pair = tokens.issue_tokens(user)
    row = OutstandingToken.objects.get(jti=decoded(pair.refresh)["jti"])
    assert row.token == tokens.digest(pair.refresh) and pair.refresh not in row.token
    with connection.cursor() as cursor:  # the token string appears nowhere in the table
        cursor.execute(
            "SELECT count(*) FROM token_blacklist_outstandingtoken t WHERE t::text LIKE %s",
            [f"%{pair.refresh[:40]}%"],
        )
        assert cursor.fetchone()[0] == 0


def test_access_tokens_are_never_stored(user):
    pair = tokens.issue_tokens(user)
    assert OutstandingToken.objects.count() == 1 and not OutstandingToken.objects.filter(
        jti=decoded(pair.access)["jti"]
    )


# --- reading access tokens ---------------------------------------------------------------------------


def test_valid_access_token_authenticates(user):
    found, claims = tokens.read_access(tokens.issue_tokens(user).access)
    assert found == user and claims.epoch == 0


def test_a_refresh_token_is_not_an_access_token_and_vice_versa(user):
    pair = tokens.issue_tokens(user)
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(pair.refresh)
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(pair.access)


def forgeries(user):
    data = forge.payload(user)
    rs_token, public_pem = forge.rs256(data)
    good = tokens.issue_tokens(user).access
    return {
        "alg_none": forge.unsigned(data),
        "alg_none_empty_signature": forge.unsigned(data) + ".",
        "wrong_key": forge.sign(data, key="x" * 64),
        "hs512_with_the_right_key": forge.sign(data, algorithm="HS512"),
        "rs256": rs_token,
        "hs256_signed_with_a_public_key": forge.hs256_with_secret(data, public_pem),
        "tampered_sub": forge.tamper_payload(good, sub="00000000-0000-4000-8000-000000000000"),
        "tampered_epoch": forge.tamper_payload(good, auth_epoch=99),
        "tampered_type": forge.tamper_payload(tokens.issue_tokens(user).refresh, token_type="access"),
        "flipped_signature": forge.flip_signature(good),
        "truncated": good[:-10],
        "empty": "",
        "dots_only": "..",
        "not_a_jwt": "hello",
        "five_parts": good + ".extra.part",
        "huge": "A" * 5000,
    }


FORGERY_NAMES = [
    "alg_none",
    "alg_none_empty_signature",
    "wrong_key",
    "hs512_with_the_right_key",
    "rs256",
    "hs256_signed_with_a_public_key",
    "tampered_sub",
    "tampered_epoch",
    "tampered_type",
    "flipped_signature",
    "truncated",
    "empty",
    "dots_only",
    "not_a_jwt",
    "five_parts",
    "huge",
]


@pytest.mark.parametrize("name", FORGERY_NAMES)
def test_forged_and_malformed_tokens_are_rejected(name, user):
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(forgeries(user)[name])


@pytest.mark.parametrize("missing", forge.CLAIMS)
def test_tokens_missing_any_required_claim_are_rejected(missing, user):
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(forge.sign(forge.payload(user, **{missing: ...})))


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "someone-else"},
        {"aud": "another-audience"},
        {"token_type": "refresh"},
        {"token_type": "ACCESS"},
        {"token_type": None},
        {"sub": "not-a-uuid"},
        {"sub": 12345},
        {"sub": None},
        {"auth_epoch": "0"},
        {"auth_epoch": True},
        {"auth_epoch": 0.0},
        {"auth_epoch": -1},
        {"jti": ""},
        {"jti": 7},
        {"exp": "tomorrow"},
        {"exp": True},
        {"iat": "now"},
        {"iat": True},
        {"iat": 4_102_444_800},  # year 2100: issued in the future
    ],
)
def test_validly_signed_but_malformed_claims_are_rejected(override, user):
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(forge.sign(forge.payload(user, **override)))


def test_an_audience_list_that_includes_ours_is_valid_per_rfc_7519(user):
    found, _ = tokens.read_access(forge.sign(forge.payload(user, aud=[forge.settings.JWT_AUDIENCE, "other"])))
    assert found == user


def test_a_correctly_built_forgery_with_the_real_key_is_accepted_proving_the_helper_is_sound(user):
    found, _ = tokens.read_access(forge.sign(forge.payload(user)))
    assert found == user  # so every rejection above is caused by the one thing it varies


def test_expired_access_token(user):
    with freeze_time("2026-10-11 12:00:00") as clock:
        pair = tokens.issue_tokens(user)
        clock.tick(899)
        assert tokens.read_access(pair.access)[0] == user
        clock.tick(2)
        with pytest.raises(tokens.InvalidToken):
            tokens.read_access(pair.access)


@pytest.mark.parametrize("change", ["epoch", "deactivated", "deleted"])
def test_user_state_changes_kill_access_tokens(change, user):
    pair = tokens.issue_tokens(user)
    if change == "epoch":
        user.bump_auth_epoch()
    elif change == "deactivated":
        User.objects.filter(pk=user.pk).update(is_active=False)  # isolate the is_active check from the epoch
    else:
        User.objects.filter(pk=user.pk).delete()
    with pytest.raises(tokens.InvalidToken):
        tokens.read_access(pair.access)


def test_roles_claim_is_ignored_for_authorisation(make_user):
    sales = make_user(ROLE_SALES_FOLLOW_UP)
    forged = forge.sign(forge.payload(sales, roles=["Admin"]))
    found, _ = tokens.read_access(forged)
    assert found.capabilities() == User.objects.get(pk=sales.pk).capabilities() and not found.has_capability(
        "retry_policy.write"
    )


# --- rotation and reuse detection --------------------------------------------------------------------


def test_rotation_issues_a_new_pair_and_kills_the_old_refresh_token(user):
    first = tokens.issue_tokens(user)
    second = tokens.rotate_tokens(first.refresh)
    assert second.refresh != first.refresh and decoded(second.refresh)["jti"] != decoded(first.refresh)["jti"]
    assert tokens.read_access(second.access)[0] == user
    assert BlacklistedToken.objects.filter(token__jti=decoded(first.refresh)["jti"]).exists()
    third = tokens.rotate_tokens(second.refresh)  # the chain continues
    assert tokens.read_access(third.access)[0] == user


def test_reusing_a_rotated_refresh_token_revokes_every_session(user, caplog):
    other_session = tokens.issue_tokens(user)
    first = tokens.issue_tokens(user)
    second = tokens.rotate_tokens(first.refresh)  # the legitimate client rotates...
    with caplog.at_level(logging.WARNING), pytest.raises(tokens.RefreshReuseDetected):
        tokens.rotate_tokens(first.refresh)  # ...then a thief replays the old token
    assert User.objects.get(pk=user.pk).auth_epoch == 1
    for victim in (other_session, second):  # every session of the user is dead, including the newest
        with pytest.raises(tokens.InvalidToken):
            tokens.read_access(victim.access)
        with pytest.raises(tokens.InvalidToken):
            tokens.rotate_tokens(victim.refresh)
    event = AuditEvent.objects.get(action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED)
    assert event.metadata == {"jti": decoded(first.refresh)["jti"]} and event.outcome == "failure"
    assert event.actor_label == user.email and event.object_id == str(user.pk)
    record = next(r for r in caplog.records if "reuse detected" in r.getMessage())
    assert record.user_id == str(user.pk) and record.jti == decoded(first.refresh)["jti"]
    assert (
        first.refresh not in caplog.text
        and second.refresh not in caplog.text
        and user.email not in caplog.text
    )


def test_the_revocation_survives_the_failed_request(user):
    first = tokens.issue_tokens(user)
    tokens.rotate_tokens(first.refresh)
    with pytest.raises(tokens.RefreshReuseDetected):
        tokens.rotate_tokens(first.refresh)
    assert User.objects.get(pk=user.pk).auth_epoch == 1  # the exception did not roll the bump back


def test_logout_then_reuse_of_the_refresh_token_is_detected(user):
    pair = tokens.issue_tokens(user)
    assert tokens.revoke_refresh(pair.refresh) is True
    with pytest.raises(tokens.RefreshReuseDetected):
        tokens.rotate_tokens(pair.refresh)
    assert User.objects.get(pk=user.pk).auth_epoch == 1


def test_revoking_twice_or_revoking_garbage_is_silent_and_idempotent(user):
    pair = tokens.issue_tokens(user)
    assert tokens.revoke_refresh(pair.refresh) is True
    assert tokens.revoke_refresh(pair.refresh) is True
    for junk in ("", "garbage", pair.access, forge.unsigned(forge.payload(user, "refresh"))):
        assert tokens.revoke_refresh(junk) is False
    assert User.objects.get(pk=user.pk).auth_epoch == 0 and BlacklistedToken.objects.count() == 1


def test_revoking_a_signed_token_we_never_issued_changes_nothing(user):
    never_issued = forge.sign(forge.payload(user, "refresh", lifetime=3600))
    assert tokens.revoke_refresh(never_issued) is False and not BlacklistedToken.objects.exists()


def test_revoke_does_not_touch_other_sessions(user):
    keep, drop = tokens.issue_tokens(user), tokens.issue_tokens(user)
    tokens.revoke_refresh(drop.refresh)
    assert tokens.read_access(keep.access)[0] == user
    tokens.rotate_tokens(keep.refresh)


def test_a_stale_epoch_refresh_token_is_invalid_not_theft(user):
    pair = tokens.issue_tokens(user)
    user.bump_auth_epoch()
    with pytest.raises(tokens.InvalidToken) as exc:
        tokens.rotate_tokens(pair.refresh)
    assert (
        not isinstance(exc.value, tokens.RefreshReuseDetected)
        and User.objects.get(pk=user.pk).auth_epoch == 1
    )
    assert not AuditEvent.objects.filter(action=actions.AUTH_TOKEN_REFRESH_REUSE_DETECTED).exists()


def test_refresh_for_deactivated_user_fails_without_blacklisting(user):
    pair = tokens.issue_tokens(user)
    User.objects.filter(pk=user.pk).update(is_active=False)
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(pair.refresh)
    assert not BlacklistedToken.objects.exists()


def test_a_correctly_signed_token_we_never_issued_is_refused(user):
    """Even with the signing key, a refresh token that was not recorded at issue time cannot be exchanged."""
    never_issued = forge.sign(forge.payload(user, "refresh", lifetime=3600))
    with pytest.raises(tokens.InvalidToken) as exc:
        tokens.rotate_tokens(never_issued)
    assert not isinstance(exc.value, tokens.RefreshReuseDetected)


def test_expired_refresh_token(user):
    with freeze_time("2026-10-11 12:00:00") as clock:
        pair = tokens.issue_tokens(user)
        clock.tick(86400 + 1)
        with pytest.raises(tokens.InvalidToken):
            tokens.rotate_tokens(pair.refresh)


def test_reuse_by_a_user_deleted_meanwhile_does_not_crash(user):
    first = tokens.issue_tokens(user)
    tokens.rotate_tokens(first.refresh)
    User.objects.filter(pk=user.pk).delete()
    with pytest.raises(tokens.InvalidToken):
        tokens.rotate_tokens(first.refresh)


def test_housekeeping_command_removes_expired_rows_and_keeps_live_ones(user):
    with freeze_time("2026-10-11 12:00:00") as clock:
        old = tokens.issue_tokens(user)
        tokens.revoke_refresh(old.refresh)
        clock.tick(86400 + 60)
        fresh = tokens.issue_tokens(user)
        call_command("flushexpiredtokens")
    assert list(OutstandingToken.objects.values_list("jti", flat=True)) == [decoded(fresh.refresh)["jti"]]
    assert not BlacklistedToken.objects.exists()
