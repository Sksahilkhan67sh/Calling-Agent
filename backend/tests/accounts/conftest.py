import itertools

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import sync_roles

PASSWORD = "correct horse battery staple 7"
_counter = itertools.count()


@pytest.fixture
def roles(db):
    sync_roles()


@pytest.fixture
def make_user(roles):
    def factory(*role_names: str, **extra) -> User:
        user = User.objects.create_user(f"user{next(_counter)}@example.com", PASSWORD, **extra)
        for name in role_names:
            user.groups.add(Group.objects.get(name=name))
        return User.objects.get(pk=user.pk)  # fresh instance: no stale capability cache

    return factory


@pytest.fixture
def api_as():
    def factory(user: User | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    return factory
