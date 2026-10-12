"""Account services. Currently: role/permission synchronisation from the code registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.roles import ALL_ROLES, ROLE_CAPABILITIES


@dataclass
class SyncResult:
    groups_created: list[str] = field(default_factory=list)
    permissions_added: dict[str, list[str]] = field(default_factory=dict)
    permissions_removed: dict[str, list[str]] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.groups_created or self.permissions_added or self.permissions_removed)


def _label(permission: Permission) -> str:
    return f"{permission.content_type.app_label}.{permission.codename}"


def sync_roles() -> SyncResult:
    """Make the Groups and their permissions match ``ROLE_CAPABILITIES`` exactly. Idempotent.

    Anything a role holds that the matrix does not grant (for example a permission added by hand) is
    removed: the code registry, not the database, is the source of truth.
    """
    create_permissions(apps.get_app_config("accounts"), verbosity=0)
    result = SyncResult()
    with transaction.atomic():
        content_type = ContentType.objects.get_for_model(User)
        available = {p.codename: p for p in Permission.objects.filter(content_type=content_type)}
        for role in ALL_ROLES:
            wanted_names = ROLE_CAPABILITIES[role]
            missing = wanted_names - available.keys()
            if missing:  # fail closed: never continue with a partial matrix
                raise RuntimeError(f"Permissions missing for capabilities: {sorted(missing)}")
            group, created = Group.objects.get_or_create(name=role)
            if created:
                result.groups_created.append(role)
            wanted = {available[name].pk: available[name] for name in wanted_names}
            current = {p.pk: p for p in group.permissions.select_related("content_type")}
            to_add = [wanted[pk] for pk in wanted.keys() - current.keys()]
            to_remove = [current[pk] for pk in current.keys() - wanted.keys()]
            if to_add:
                group.permissions.add(*to_add)
                result.permissions_added[role] = sorted(_label(p) for p in to_add)
            if to_remove:
                group.permissions.remove(*to_remove)
                result.permissions_removed[role] = sorted(_label(p) for p in to_remove)
    return result
