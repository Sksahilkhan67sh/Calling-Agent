"""No endpoint without declared permissions (Django-Backend-Design §8).

Walks the URL conf; fails for any view that is not DRF, declares no permission classes,
or silently inherits the default deny. Anonymous access is allowed only for the reviewed
allowlist below.
"""

import pytest
from django.urls import URLPattern, URLResolver
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.health import HealthLive, HealthReady
from apps.core.permissions import DefaultDeny, PublicEndpoint
from config.urls import build_urlpatterns

# Reviewed anonymous surface. Docs views exist only when ENABLE_API_DOCS (dev) is true.
ANONYMOUS_ALLOWLIST = {
    "HealthLive",
    "HealthReady",
    "SpectacularAPIView",
    "SpectacularSwaggerView",
    "SpectacularRedocView",
}


def _views(patterns):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _views(entry.url_patterns)
        elif isinstance(entry, URLPattern):
            yield str(entry.pattern), entry.callback


def find_violations(patterns) -> list[str]:
    problems: list[str] = []
    for route, callback in _views(patterns):
        cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
        if cls is None or not (isinstance(cls, type) and issubclass(cls, APIView)):
            problems.append(f"{route}: not a DRF view")
            continue
        perms = list(cls.permission_classes)
        if not perms:
            problems.append(f"{route}: {cls.__name__} has empty permission_classes (open to everyone)")
        elif all(p is DefaultDeny for p in perms):
            problems.append(f"{route}: {cls.__name__} declares no permissions (default deny)")
        elif any(p in (PublicEndpoint, AllowAny) for p in perms) and cls.__name__ not in ANONYMOUS_ALLOWLIST:
            problems.append(f"{route}: {cls.__name__} is anonymous but not in the reviewed allowlist")
    return problems


@pytest.mark.parametrize("docs", [False, True])
def test_every_view_declares_permissions(docs):
    patterns = build_urlpatterns(enable_api_docs=docs)
    assert len(list(_views(patterns))) == (5 if docs else 2)
    assert find_violations(patterns) == []


def test_negative_undeclared_view_is_detected():
    class Undeclared(APIView):
        def get(self, request):  # pragma: no cover - never called
            ...

    class OpenView(APIView):
        permission_classes: list = []

    class SneakyAnonymous(APIView):
        permission_classes = [PublicEndpoint]

    from django.urls import path

    patterns = [
        path("a", Undeclared.as_view()),
        path("b", OpenView.as_view()),
        path("c", SneakyAnonymous.as_view()),
        path("d", lambda request: None),
        path("ok", HealthLive.as_view()),
    ]
    problems = find_violations(patterns)
    assert len(problems) == 4 and not any("ok:" in p for p in problems)


def test_default_permission_is_deny_and_denies(client):
    from rest_framework.test import APIRequestFactory

    class Plain(APIView):
        def get(self, request):  # pragma: no cover
            ...

    response = Plain.as_view()(APIRequestFactory().get("/x"))
    assert response.status_code == 403


def test_health_views_are_in_allowlist():
    assert {HealthLive.__name__, HealthReady.__name__} <= ANONYMOUS_ALLOWLIST
