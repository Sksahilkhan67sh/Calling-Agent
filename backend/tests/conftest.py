import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

PASSWORD = "correct-horse-battery-staple"
LOGIN = "/v1/auth/token"


@pytest.fixture
def make_user(db):
    def _make(username="u1", role=None, active=True):
        from django.contrib.auth.models import Group

        user = get_user_model().objects.create_user(username, password=PASSWORD, is_active=active)
        if role:
            user.groups.add(Group.objects.get(name=role))
        return user

    return _make


@pytest.fixture
def client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def login(client):
    def _login(username="u1", **extra):
        return client.post(LOGIN, {"username": username, "password": PASSWORD, **extra}, format="json")

    return _login


def csrf(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}
