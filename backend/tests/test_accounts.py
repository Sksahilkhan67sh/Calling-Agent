import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_uuid_pk_and_login_field():
    user = User.objects.create_user("Alice@Example.COM", "a-long-password-123")
    assert isinstance(user.pk, uuid.UUID) and user.email == "alice@example.com"
    assert User.USERNAME_FIELD == "email"
    assert "username" not in [f.name for f in User._meta.get_fields()]


def test_email_unique_case_insensitive_at_db_level():
    User.objects.create_user("bob@example.com", "a-long-password-123")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("BOB@example.com", "a-long-password-123")
    with pytest.raises(IntegrityError), transaction.atomic():  # bypasses save() normalisation
        User.objects.bulk_create([User(email="Bob@Example.com", password="x")])


def test_password_hashed_with_argon2(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
    user = User.objects.create_user("c@example.com", "a-long-password-123")
    assert user.password.startswith("argon2$") and user.check_password("a-long-password-123")


def test_superuser_flags_and_missing_email():
    admin = User.objects.create_superuser("root@example.com", "a-long-password-123")
    assert admin.is_staff and admin.is_superuser
    with pytest.raises(ValueError):
        User.objects.create_user("", "x")
