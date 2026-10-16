"""HasCapability: default deny, fail closed, no superuser bypass (P2-05)."""

import logging

import pytest
from django.contrib.auth.models import Permission
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.accounts.permissions import CapabilityPermission, HasCapability
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP, ROLE_SYSTEM

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def decide(permission, user, auth=None) -> bool:
    request = Request(APIRequestFactory().get("/x"))
    request.user = user
    request.auth = auth
    return permission().has_permission(request, APIView())


def test_factory_validates_names_and_caches_classes():
    assert HasCapability("campaigns.create") is HasCapability("campaigns.create")
    assert HasCapability("campaigns.create") is not HasCapability("campaigns.view_own")
    assert issubclass(HasCapability("campaigns.create"), CapabilityPermission)
    with pytest.raises(ValueError, match="Unknown capability"):
        HasCapability("campaigns.creat")  # a typo fails at import time, not at runtime
    with pytest.raises(ValueError, match="at least one"):
        HasCapability()


def test_anonymous_and_missing_users_are_denied():
    assert decide(HasCapability("campaigns.create"), None) is False

    class Anonymous:
        is_authenticated = False

    assert decide(HasCapability("campaigns.create"), Anonymous()) is False


@pytest.mark.parametrize(
    ("role", "capability", "allowed"),
    [
        (ROLE_CAMPAIGN_MANAGER, "campaigns.create", True),
        (ROLE_CAMPAIGN_MANAGER, "retry_policy.write", False),
        (ROLE_CAMPAIGN_MANAGER, "suppression.manage", False),
        (ROLE_ADMIN, "retry_policy.write", True),
        (ROLE_SALES_FOLLOW_UP, "final_output.view", True),
        (ROLE_SALES_FOLLOW_UP, "campaigns.create", False),
        (ROLE_SALES_FOLLOW_UP, "contacts.suppress", False),
        (ROLE_SALES_FOLLOW_UP, "recordings.listen", False),
        (ROLE_SYSTEM, "campaigns.view_all", False),
    ],
)
def test_roles_grant_exactly_their_capabilities(role, capability, allowed, make_user):
    assert decide(HasCapability(capability), make_user(role)) is allowed


def test_user_without_roles_has_nothing(make_user):
    assert make_user().capabilities() == frozenset()


def test_any_of_semantics(make_user):
    either = HasCapability("campaigns.view_all", "retry_policy.write")
    assert decide(either, make_user(ROLE_ADMIN)) is True
    assert decide(either, make_user(ROLE_CAMPAIGN_MANAGER)) is False


def test_superuser_flag_does_not_bypass_rbac(make_user):
    superuser = make_user(is_superuser=True, is_staff=True)
    assert superuser.has_perm("accounts.campaigns.create") is True  # Django's own shortcut says yes...
    assert decide(HasCapability("campaigns.create"), superuser) is False  # ...ours says no
    assert superuser.capabilities() == frozenset()


def test_inactive_user_with_a_role_has_no_capabilities(make_user):
    user = make_user(ROLE_ADMIN)
    user.is_active = False
    user.save()
    assert type(user).objects.get(pk=user.pk).capabilities() == frozenset()


def test_unsaved_user_has_nothing():
    from apps.accounts.models import User

    assert User(email="new@example.com").capabilities() == frozenset()


def test_per_user_grant_is_honoured_and_isolated(make_user):
    granted, other = make_user(ROLE_CAMPAIGN_MANAGER), make_user(ROLE_CAMPAIGN_MANAGER)
    assert decide(HasCapability("recordings.listen"), granted) is False
    granted.user_permissions.add(Permission.objects.get(codename="recordings.listen"))
    granted.refresh_from_db()
    assert decide(HasCapability("recordings.listen"), granted) is True
    assert decide(HasCapability("recordings.listen"), other) is False


def test_capability_cache_is_per_instance_and_cleared_by_refresh(make_user, roles):
    from django.contrib.auth.models import Group

    user = make_user()
    assert user.has_capability("campaigns.create") is False
    user.groups.add(Group.objects.get(name=ROLE_CAMPAIGN_MANAGER))
    assert user.has_capability("campaigns.create") is False  # cached for this request's lifetime
    user.refresh_from_db()
    assert user.has_capability("campaigns.create") is True


def test_unknown_capability_name_is_false_not_an_error(make_user):
    assert make_user(ROLE_ADMIN).has_capability("made.up") is False


def test_other_apps_permissions_never_become_capabilities(make_user):
    from django.contrib.auth.models import Group

    admin = make_user(ROLE_ADMIN)
    Group.objects.get(name=ROLE_ADMIN).permissions.add(Permission.objects.get(codename="add_group"))
    admin.refresh_from_db()
    assert "add_group" not in admin.capabilities()


def test_principal_without_has_capability_is_denied():
    class Odd:
        is_authenticated = True

    assert decide(HasCapability("campaigns.create"), Odd()) is False


def test_non_boolean_answers_are_not_trusted():
    class Sloppy:
        is_authenticated = True

        def has_capability(self, name):
            return "yes"  # truthy but not True

    assert decide(HasCapability("campaigns.create"), Sloppy()) is False


def test_errors_during_the_check_deny_and_log_without_secrets(caplog):
    class Broken:
        is_authenticated = True

        def has_capability(self, name):
            raise RuntimeError("db exploded: password=hunter2")

    with caplog.at_level(logging.ERROR):
        assert decide(HasCapability("campaigns.create"), Broken()) is False
    record = next(r for r in caplog.records if "capability check failed" in r.getMessage())
    assert record.capabilities == ["campaigns.create"]


def test_api_exceptions_are_not_swallowed():
    class Rejecting:
        is_authenticated = True

        def has_capability(self, name):
            raise NotAuthenticated()

    with pytest.raises(NotAuthenticated):
        decide(HasCapability("campaigns.create"), Rejecting())


def test_restricted_credentials_never_grant_capabilities(make_user):
    class Restricted:
        restricted = True

    admin = make_user(ROLE_ADMIN)
    assert decide(HasCapability("campaigns.create"), admin) is True
    assert decide(HasCapability("campaigns.create"), admin, auth=Restricted()) is False


def test_a_plain_django_request_without_auth_information_is_denied(make_user):
    request = APIRequestFactory().get("/x")  # not a DRF Request: no .auth attribute
    request.user = make_user(ROLE_ADMIN)
    assert HasCapability("campaigns.create")().has_permission(request, APIView()) is False
