"""sync_roles: creates, converges, is idempotent and removes drift (P2-04)."""

from io import StringIO

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from apps.accounts.roles import (
    ALL_ROLES,
    CAPABILITY_NAMES,
    ROLE_CAMPAIGN_MANAGER,
    ROLE_CAPABILITIES,
    ROLE_SYSTEM,
)
from apps.accounts.services import sync_roles

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def held(role: str) -> set[str]:
    group = Group.objects.get(name=role)
    return {
        f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.select_related("content_type")
    }


def test_first_run_creates_every_group_and_permission():
    Group.objects.all().delete()
    result = sync_roles()
    assert sorted(result.groups_created) == sorted(ALL_ROLES) and result.changed
    for role in ALL_ROLES:
        assert held(role) == {f"accounts.{c}" for c in ROLE_CAPABILITIES[role]}
    assert Group.objects.get(name=ROLE_SYSTEM).permissions.count() == 0


def test_every_registry_capability_exists_as_a_permission():
    sync_roles()
    codenames = set(
        Permission.objects.filter(content_type__app_label="accounts").values_list("codename", flat=True)
    )
    assert codenames >= CAPABILITY_NAMES


def test_second_run_is_a_no_op():
    sync_roles()
    again = sync_roles()
    assert not again.changed and again.groups_created == [] and again.permissions_added == {}


def test_command_is_idempotent_and_reports_state():
    out = StringIO()
    call_command("sync_roles", stdout=out)
    out2 = StringIO()
    call_command("sync_roles", stdout=out2)
    assert out2.getvalue().strip() == "Roles already in sync."


def test_drift_is_repaired_in_both_directions():
    sync_roles()
    group = Group.objects.get(name=ROLE_CAMPAIGN_MANAGER)
    stray = Permission.objects.get(content_type__app_label="auth", codename="add_group")
    needed = Permission.objects.get(content_type__app_label="accounts", codename="campaigns.create")
    group.permissions.add(stray)
    group.permissions.remove(needed)
    result = sync_roles()
    assert result.permissions_added == {ROLE_CAMPAIGN_MANAGER: ["accounts.campaigns.create"]}
    assert result.permissions_removed == {ROLE_CAMPAIGN_MANAGER: ["auth.add_group"]}
    assert held(ROLE_CAMPAIGN_MANAGER) == {f"accounts.{c}" for c in ROLE_CAPABILITIES[ROLE_CAMPAIGN_MANAGER]}


def test_system_group_drift_is_removed():
    sync_roles()
    Group.objects.get(name=ROLE_SYSTEM).permissions.add(Permission.objects.get(codename="recordings.listen"))
    assert sync_roles().permissions_removed == {ROLE_SYSTEM: ["accounts.recordings.listen"]}
    assert held(ROLE_SYSTEM) == set()


def test_per_user_grants_are_not_touched_by_sync():
    from apps.accounts.models import User

    sync_roles()
    user = User.objects.create_user("grant@example.com", "correct horse battery staple 7")
    user.user_permissions.add(Permission.objects.get(codename="recordings.listen"))
    assert not sync_roles().changed
    assert user.user_permissions.filter(codename="recordings.listen").exists()


def test_missing_permission_fails_closed(monkeypatch):
    from apps.accounts import services

    sync_roles()
    monkeypatch.setattr(services, "create_permissions", lambda *a, **k: None)
    Permission.objects.filter(codename="audit.view").delete()
    with pytest.raises(RuntimeError, match="audit.view"):
        sync_roles()


def test_command_reports_what_it_changed():
    sync_roles()
    group = Group.objects.get(name=ROLE_CAMPAIGN_MANAGER)
    group.permissions.add(Permission.objects.get(content_type__app_label="auth", codename="add_group"))
    Group.objects.filter(name=ROLE_SYSTEM).delete()
    out = StringIO()
    call_command("sync_roles", stdout=out)
    text = out.getvalue()
    assert f"created group: {ROLE_SYSTEM}" in text and "-1 permissions (drift removed)" in text
