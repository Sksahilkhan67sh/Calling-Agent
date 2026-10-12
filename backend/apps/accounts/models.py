import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.roles import CAPABILITIES


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        return (email or "").strip().lower()

    def _create(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    """A human dashboard user. Email is the identity; there is no self-service signup.

    ``auth_epoch`` is the session-revocation lever: every access and refresh token carries the epoch it was
    issued under and is rejected once the user's epoch has moved on. The epoch only ever increases, and only
    through ``bump_auth_epoch`` (an atomic database increment); ``save()`` never writes it, so a stale
    in-memory copy cannot roll it back and revive revoked tokens.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True, default="", db_default="")
    auth_epoch = models.PositiveIntegerField(default=0, db_default=0, editable=False)
    password_changed_at = models.DateTimeField(null=True, blank=True, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    objects = UserManager()  # type: ignore[assignment,misc]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]
        # Capabilities are custom permissions; the registry in roles.py is the single source.
        permissions = [(c.name, c.description) for c in CAPABILITIES]

    def save(self, **kwargs: Any) -> None:
        """Persist the user. A password change or a deactivation revokes all of the user's sessions.

        Detection compares against the row locked inside this transaction, so no caller can forget the
        revocation and concurrent saves cannot both miss it.
        """
        self.email = UserManager.normalize_email(self.email)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "auth_epoch" in update_fields:
            raise ValueError("auth_epoch is changed only by bump_auth_epoch()")
        if self._state.adding:
            if self.password_changed_at is None:
                self.password_changed_at = timezone.now()
            super().save(**kwargs)
            return

        using = kwargs.get("using") or self._state.db
        with transaction.atomic(using=using):
            stored = (
                type(self)
                ._base_manager.using(using)
                .select_for_update()
                .only("password", "is_active")
                .get(pk=self.pk)  # a deleted user must not be re-created (and un-revoked) by a stale save
            )
            password_changed = stored.password != self.password
            deactivated = stored.is_active and not self.is_active
            if password_changed:
                self.password_changed_at = timezone.now()
            if update_fields is None:
                kwargs["update_fields"] = [
                    f.name for f in self._meta.concrete_fields if not f.primary_key and f.name != "auth_epoch"
                ]
            elif password_changed:
                kwargs["update_fields"] = {*update_fields, "password_changed_at"}
            super().save(**kwargs)
            if password_changed or deactivated:
                self.bump_auth_epoch()

    def bump_auth_epoch(self) -> None:
        """Invalidate every outstanding token of this user. Atomic and monotonic in the database."""
        if self._state.adding:
            raise ValueError("Cannot bump the auth epoch of an unsaved user")
        type(self)._base_manager.filter(pk=self.pk).update(auth_epoch=F("auth_epoch") + 1)
        self.refresh_from_db(fields=["auth_epoch"])

    def role_names(self) -> frozenset[str]:
        return frozenset(group.name for group in self.groups.all())

    @property
    def requires_mfa(self) -> bool:
        """True when any of the user's roles is in ``MFA_REQUIRED_ROLES``. Computed, never stored."""
        return bool(self.role_names() & set(settings.MFA_REQUIRED_ROLES))
