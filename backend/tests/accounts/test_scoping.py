"""Object-level scoping through real views: no existence leaks, no escalation (P2-05)."""

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import ImproperlyConfigured
from rest_framework.generics import ListAPIView
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.accounts.querysets import ScopedQuerySet, ScopedViewMixin
from apps.accounts.roles import ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP
from tests.testapp.models import ScopedThing
from tests.testapp.views import ThingSerializer

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.urls("tests.testapp.urls")]


@pytest.fixture
def world(make_user):
    alice, bob = make_user(ROLE_CAMPAIGN_MANAGER), make_user(ROLE_CAMPAIGN_MANAGER)
    admin, sales = make_user(ROLE_ADMIN), make_user(ROLE_SALES_FOLLOW_UP)
    mine = ScopedThing.objects.create(owner=alice, title="alice-1")
    theirs = ScopedThing.objects.create(owner=bob, title="bob-1")
    return {"alice": alice, "bob": bob, "admin": admin, "sales": sales, "mine": mine, "theirs": theirs}


def titles(response) -> set[str]:
    return {row["title"] for row in response.json()}


def test_manager_lists_only_own_rows(world, api_as):
    response = api_as(world["alice"]).get("/things/")
    assert response.status_code == 200 and titles(response) == {"alice-1"}


def test_admin_lists_every_row(world, api_as):
    assert titles(api_as(world["admin"]).get("/things/")) == {"alice-1", "bob-1"}


def test_detail_of_another_managers_row_is_404_not_403(world, api_as):
    response = api_as(world["alice"]).get(f"/things/{world['theirs'].pk}/")
    assert response.status_code == 404


def test_guessing_a_uuid_is_indistinguishable_from_a_foreign_row(world, api_as):
    client = api_as(world["alice"])
    foreign = client.get(f"/things/{world['theirs'].pk}/")
    random = client.get(f"/things/{uuid.uuid4()}/")
    assert foreign.status_code == random.status_code == 404
    assert foreign.json() == random.json()


def test_own_detail_and_admin_detail_work(world, api_as):
    assert api_as(world["alice"]).get(f"/things/{world['mine'].pk}/").status_code == 200
    assert api_as(world["admin"]).get(f"/things/{world['theirs'].pk}/").status_code == 200


def test_cannot_modify_another_managers_row(world, api_as):
    response = api_as(world["alice"]).patch(f"/things/{world['theirs'].pk}/status/", {"status": "paused"})
    assert response.status_code == 404
    world["theirs"].refresh_from_db()
    assert world["theirs"].status == "draft"
    assert (
        api_as(world["alice"]).patch(f"/things/{world['mine'].pk}/status/", {"status": "paused"}).status_code
        == 200
    )


def test_anonymous_requests_are_rejected(world, api_as):
    assert api_as(None).get("/things/").status_code in (401, 403)
    assert api_as(None).get(f"/things/{world['mine'].pk}/").status_code in (401, 403)


def test_sales_cannot_write_or_list_campaign_data(world, api_as):
    sales = api_as(world["sales"])
    assert sales.post("/things/new/", {"title": "x"}).status_code == 403
    assert sales.patch(f"/things/{world['mine'].pk}/status/", {"status": "paused"}).status_code == 403
    assert sales.get("/things/").status_code == 403
    assert ScopedThing.objects.count() == 2


def test_manager_creates_rows_owned_by_themselves(world, api_as):
    response = api_as(world["alice"]).post("/things/new/", {"title": "alice-2"})
    assert response.status_code == 201
    assert ScopedThing.objects.get(pk=response.json()["id"]).owner == world["alice"]


@pytest.mark.parametrize("who", ["alice", "sales"])
def test_privilege_escalation_to_admin_capability_is_refused(who, world, api_as):
    assert api_as(world[who]).put("/retry-policy/").status_code == 403
    assert api_as(world["admin"]).put("/retry-policy/").status_code == 200


def test_recordings_need_an_explicit_per_user_grant(world, api_as):
    url = f"/things/{world['mine'].pk}/recording/"
    for role in ("alice", "admin", "sales"):  # no role holds it, not even Admin
        assert api_as(world[role]).get(url).status_code == 403
    world["alice"].user_permissions.add(Permission.objects.get(codename="recordings.listen"))
    granted = User.objects.get(pk=world["alice"].pk)
    assert api_as(granted).get(url).status_code == 200
    assert api_as(world["bob"]).get(url).status_code == 403


def test_view_all_alone_is_enough_to_list_everything(world, make_user, api_as):
    reader = make_user()
    reader.user_permissions.add(Permission.objects.get(codename="campaigns.view_all"))
    reader = User.objects.get(pk=reader.pk)
    assert titles(api_as(reader).get("/things/")) == {"alice-1", "bob-1"}


def test_for_user_returns_nothing_without_a_principal_or_capability(world, make_user):
    assert not ScopedThing.objects.for_user(None).exists()
    assert not ScopedThing.objects.for_user(AnonymousUser()).exists()
    assert not ScopedThing.objects.for_user(make_user()).exists()  # authenticated, but holds nothing
    assert not ScopedThing.objects.for_user(world["sales"]).exists()


@pytest.mark.urls("tests.testapp.urls_unscoped")
def test_object_scoped_backstop_hides_foreign_objects(world, api_as):
    client = api_as(world["alice"])
    assert client.get(f"/unscoped/{world['mine'].pk}/").status_code == 200
    assert client.get(f"/unscoped/{world['theirs'].pk}/").status_code == 404


def test_scoped_queryset_must_implement_scope_to_user(world):
    class Unfinished(ScopedQuerySet):
        pass

    with pytest.raises(NotImplementedError, match="scope_to_user"):
        Unfinished(model=ScopedThing).for_user(world["alice"])


def test_view_all_capability_is_optional():
    class NoBypass(ScopedQuerySet):
        def scope_to_user(self, user):
            return self.none()

    class Everything:
        is_authenticated = True

        def has_capability(self, name):
            return True

    assert not NoBypass(model=ScopedThing).for_user(Everything()).exists()


def test_scoped_view_rejects_unscoped_querysets():
    class Misconfigured(ScopedViewMixin, ListAPIView):
        queryset = User.objects.all()
        serializer_class = ThingSerializer

    request = APIRequestFactory().get("/x")
    view = Misconfigured()
    view.request = request
    with pytest.raises(ImproperlyConfigured, match="ScopedQuerySet"):
        view.get_queryset()
