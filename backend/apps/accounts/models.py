import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager, Permission
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.roles import CAPABILITIES, CAPABILITY_NAMES


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

    _capabilities_cache: frozenset[str] | None = None

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

    def capabilities(self) -> frozenset[str]:
        """Capabilities from the user's roles (group permissions) plus per-user grants.

        Deliberately ignores ``is_superuser``: the flag must never bypass RBAC. Inactive and unsaved users
        hold nothing. Cached on the instance (one query per request); ``refresh_from_db`` clears it.
        """
        if self._capabilities_cache is None:
            if not self.is_active or self._state.adding:
                self._capabilities_cache = frozenset()
            else:
                codenames = (
                    Permission.objects.filter(
                        content_type__app_label="accounts",
                        content_type__model="user",
                        codename__in=CAPABILITY_NAMES,
                    )
                    .filter(Q(group__user=self) | Q(user=self))
                    .values_list("codename", flat=True)
                    .distinct()
                )
                self._capabilities_cache = frozenset(codenames)
        return self._capabilities_cache

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities()

    def refresh_from_db(self, *args: Any, **kwargs: Any) -> None:
        self._capabilities_cache = None
        super().refresh_from_db(*args, **kwargs)

    @property
    def has_active_mfa_device(self) -> bool:
        return self.mfa_devices.filter(confirmed_at__isnull=False, disabled_at__isnull=True).exists()

    @property
    def must_enroll_mfa(self) -> bool:
        """The user's roles require MFA and no confirmed device exists yet. Computed, never stored."""
        return self.requires_mfa and not self.has_active_mfa_device


class MfaDevice(models.Model):
    """A TOTP authenticator. The seed is stored only as AES-GCM ciphertext (``FieldCipher``), bound to
    this row, so a database copy yields no usable seeds without the encryption key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_devices")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Highest TOTP time step already accepted: a code for a step <= this is a replay.
    last_used_step = models.PositiveBigIntegerField(default=0, db_default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(confirmed_at__isnull=False, disabled_at__isnull=True),
                name="mfadevice_one_active_per_user",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(confirmed_at__isnull=True, disabled_at__isnull=True),
                name="mfadevice_one_pending_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"MfaDevice {self.pk}"
