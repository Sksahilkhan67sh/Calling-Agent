import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView


class Declared(APIView):
    roles = {"GET": {"Admin"}}

    def get(self, request):
        return Response("ok")

    def post(self, request):
        return Response("ok")


class Undeclared(APIView):
    def get(self, request):
        return Response("ok")


def call(view, user, method="get"):
    req = getattr(APIRequestFactory(), method)("/x")
    if user:
        force_authenticate(req, user=user)
    return view.as_view()(req).status_code


def test_role_matrix(make_user):
    assert call(Declared, make_user("a", "Admin")) == 200
    assert call(Declared, make_user("b", "Campaign Manager")) == 403
    assert call(Declared, make_user("c")) == 403
    assert call(Declared, make_user("d", "Admin"), "post") == 403  # method not declared
    assert call(Declared, None) in (401, 403)


def test_undeclared_view_denies_everyone(make_user):
    assert call(Undeclared, make_user("a", "Admin")) == 403


def _views(patterns):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _views(p.url_patterns)
        elif isinstance(p, URLPattern) and hasattr(p.callback, "cls"):
            yield p.callback.cls


def test_every_project_view_declares_permissions():
    undeclared = [
        v.__name__
        for v in _views(get_resolver().url_patterns)
        if v.__module__.startswith("apps.")
        and v.permission_classes is api_settings.DEFAULT_PERMISSION_CLASSES
        and not hasattr(v, "roles")
    ]
    assert not undeclared
