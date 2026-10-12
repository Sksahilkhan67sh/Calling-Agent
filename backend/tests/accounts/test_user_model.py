"""User model: session-revocation epoch, password/deactivation hooks, role-driven MFA flag (P2-03)."""

import uuid

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

PASSWORD = "correct horse battery staple 7"


@pytest.fixture
def user() -> User:
    return User.objects.create_user("epoch@example.com", PASSWORD, full_name="Edith Epoch")


def stored_epoch(user: User) -> int:
    return User.objects.values_list("auth_epoch", flat=True).get(pk=user.pk)


def test_new_user_defaults(user, frozen_time):
    assert user.auth_epoch == 0 and user.full_name == "Edith Epoch"
    assert user.password_changed_at is not None and user.is_active


def test_password_change_bumps_epoch_once_and_records_time(user, frozen_time):
    user.set_password("another correct horse 8")
    user.save()
    assert user.auth_epoch == 1 == stored_epoch(user)
    assert user.password_changed_at.isoformat().startswith("2026-10-11T12:00:00")


def test_password_change_with_update_fields_still_bumps_and_stamps(user):
    before = user.password_changed_at
    user.set_password("another correct horse 8")
    user.save(update_fields=["password"])
    fresh = User.objects.get(pk=user.pk)
    assert fresh.auth_epoch == 1 and fresh.password_changed_at > before
    assert fresh.check_password("another correct horse 8")


def test_unrelated_save_does_not_bump(user):
    user.full_name = "Edith E."
    user.save()
    assert stored_epoch(user) == 0 and User.objects.get(pk=user.pk).full_name == "Edith E."


def test_deactivation_bumps_but_reactivation_and_resave_do_not(user):
    user.is_active = False
    user.save()
    assert stored_epoch(user) == 1
    user.full_name = "still inactive"
    user.save()
    assert stored_epoch(user) == 1
    user.is_active = True
    user.save()
    assert stored_epoch(user) == 1


def test_stale_copy_cannot_roll_the_epoch_back(user):
    stale = User.objects.get(pk=user.pk)
    user.bump_auth_epoch()
    user.bump_auth_epoch()
    stale.full_name = "written from a stale copy"
    stale.save()
    assert stored_epoch(user) == 2
    assert stale.auth_epoch == 0  # the stale object is not refreshed; the database value is untouched


def test_bumps_are_relative_increments_not_absolute_writes(user):
    first, second = User.objects.get(pk=user.pk), User.objects.get(pk=user.pk)
    first.bump_auth_epoch()
    second.bump_auth_epoch()
    assert stored_epoch(user) == 2 and second.auth_epoch == 2


def test_epoch_cannot_be_written_through_update_fields(user):
    user.auth_epoch = 99
    with pytest.raises(ValueError, match="bump_auth_epoch"):
        user.save(update_fields=["auth_epoch"])
    assert stored_epoch(user) == 0


def test_cannot_bump_an_unsaved_user():
    with pytest.raises(ValueError, match="unsaved"):
        User(email="x@example.com").bump_auth_epoch()


def test_epoch_column_rejects_negative_values_at_db_level(user):
    with pytest.raises(Exception, match="auth_epoch"), connection.cursor() as cursor:
        cursor.execute("UPDATE accounts_user SET auth_epoch = -1 WHERE id = %s", [user.pk])


def test_inactive_user_cannot_authenticate(user):
    assert authenticate(email="epoch@example.com", password=PASSWORD) is not None
    user.is_active = False
    user.save()
    assert authenticate(email="epoch@example.com", password=PASSWORD) is None


@pytest.mark.parametrize(
    ("candidate", "fragment"),
    [
        ("Short1!aa", "too short"),
        ("password1234", "too common"),
        ("738495162038", "entirely numeric"),
        ("edith.epoch@example", "too similar"),
        ("EdithEpochEdith", "too similar"),
    ],
)
def test_password_validators_are_active(candidate, fragment, user):
    with pytest.raises(ValidationError) as exc:
        validate_password(candidate, user=user)
    assert fragment in " ".join(exc.value.messages)


def test_strong_password_is_accepted(user):
    validate_password(PASSWORD, user=user)


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        ([], False),
        (["Sales / Follow-up"], False),
        (["System"], False),
        (["Admin"], True),
        (["Campaign Manager"], True),
        (["Sales / Follow-up", "Campaign Manager"], True),
    ],
)
def test_requires_mfa_follows_roles(groups, expected, user):
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    assert user.requires_mfa is expected


def test_requires_mfa_honours_configured_roles(user, settings):
    user.groups.add(Group.objects.get_or_create(name="Sales / Follow-up")[0])
    assert user.requires_mfa is False
    settings.MFA_REQUIRED_ROLES = ["Admin", "Campaign Manager", "Sales / Follow-up"]
    assert user.requires_mfa is True


@pytest.mark.django_db(transaction=True)
def test_migration_0002_applies_over_phase1_data_and_reverses():
    target = ("accounts", "0002_user_epoch_and_profile")
    previous = ("accounts", "0001_initial")
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([previous])
        old_user = executor.loader.project_state([previous]).apps.get_model("accounts", "User")
        legacy_id = uuid.uuid4()
        old_user.objects.create(id=legacy_id, email="legacy@example.com", password="!")

        executor = MigrationExecutor(connection)
        executor.migrate([target])
        new_user = executor.loader.project_state([target]).apps.get_model("accounts", "User")
        row = new_user.objects.get(pk=legacy_id)
        assert (row.auth_epoch, row.full_name, row.password_changed_at) == (0, "", None)

        with (
            connection.cursor() as cursor
        ):  # rolling deploy: an older app version inserts without the new columns
            cursor.execute(
                "INSERT INTO accounts_user (id, email, password, is_superuser, first_name, last_name, "
                "is_staff, is_active, date_joined) VALUES (%s, 'old-code@example.com', '!', false, '', '', "
                "false, true, now())",
                [uuid.uuid4()],
            )
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def test_saving_a_deleted_user_does_not_resurrect_it(user):
    User.objects.filter(pk=user.pk).delete()
    with pytest.raises(User.DoesNotExist):
        user.save()
    assert not User.objects.filter(pk=user.pk).exists()
