"""No endpoint without declared permissions (Django-Backend-Design §8).

Walks the URL conf; fails for any view that is not DRF, declares no permission classes,
silently inherits the default deny, or declares no ``HasCapability``. Views without a capability
(anonymous or merely authenticated) must be on the reviewed allowlist below, each with a written
justification (Phase 2, P2-05).
"""

import pytest
from django.urls import URLPattern, URLResolver
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.permissions import CapabilityPermission, HasCapability
from apps.core.health import HealthLive, HealthReady
from apps.core.permissions import DefaultDeny, PublicEndpoint
from config.urls import build_urlpatterns

# Reviewed exceptions: views that may omit HasCapability. Every entry needs a justification.
# Adding to this dict is a security decision and must be reviewed. Auth views join in P2-09.
REVIEWED_EXCEPTIONS = {
    "HealthLive": "Liveness probe for the orchestrator; returns no data.",
    "HealthReady": "Readiness probe; reports only ok/degraded, no internals.",
    "SpectacularAPIView": "OpenAPI schema; mounted only when ENABLE_API_DOCS (dev), never in prod.",
    "SpectacularSwaggerView": "API docs UI; mounted only when ENABLE_API_DOCS (dev), never in prod.",
    "LoginView": "POST /auth/token is the credential check: anonymous by contract, throttled.",
    "RefreshView": "POST /auth/token/refresh is authenticated by the refresh cookie; CSRF-checked.",
    "CsrfView": "GET /auth/csrf only issues a CSRF cookie; it carries no data and needs no identity.",
    "MeView": (
        "GET /auth/me is identity-only: any authenticated human reads their own profile, so no capability "
        "is required; API clients and the restricted enrolment credential are refused by IsHumanSession."
    ),
    "LogoutView": (
        "POST /auth/logout is open to any caller and idempotent: it authenticates itself (access or refresh "
        "cookie), enforces CSRF when a cookie is present and only ever ends the caller's own session."
    ),
    "MfaEnrollView": "POST /auth/mfa/enroll accepts only the restricted MFA enrolment credential.",
    "MfaConfirmView": "POST /auth/mfa/confirm accepts only the restricted MFA enrolment credential.",
    "EnrollProbe": "Test-only stand-in for the MFA enrolment endpoints (restricted credential only).",
    "SpectacularRedocView": "API docs UI; mounted only when ENABLE_API_DOCS (dev), never in prod.",
}
ANONYMOUS_ALLOWLIST = set(REVIEWED_EXCEPTIONS)


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
        elif any(p in (PublicEndpoint, AllowAny) for p in perms) and cls.__name__ not in REVIEWED_EXCEPTIONS:
            problems.append(f"{route}: {cls.__name__} is anonymous but not in the reviewed allowlist")
        elif cls.__name__ not in REVIEWED_EXCEPTIONS and not any(
            isinstance(p, type) and issubclass(p, CapabilityPermission) for p in perms
        ):
            problems.append(
                f"{route}: {cls.__name__} declares no HasCapability and is not a reviewed exception"
            )
    return problems


@pytest.mark.parametrize("docs", [False, True])
def test_every_view_declares_permissions(docs):
    patterns = build_urlpatterns(enable_api_docs=docs)
    assert len(list(_views(patterns))) == (12 if docs else 9)  # probes + 7 auth views (+ 3 docs views)
    assert find_violations(patterns) == []


def test_testapp_views_all_declare_capabilities():
    from tests.testapp.urls import unscoped_patterns, urlpatterns

    assert len(list(_views(urlpatterns))) == 9
    assert find_violations([*urlpatterns, *unscoped_patterns]) == []


def test_exceptions_carry_a_written_justification():
    assert all(len(text) > 20 for text in REVIEWED_EXCEPTIONS.values())


def test_negative_undeclared_view_is_detected():
    class Undeclared(APIView):
        def get(self, request):  # pragma: no cover - never called
            ...

    class OpenView(APIView):
        permission_classes: list = []

    class SneakyAnonymous(APIView):
        permission_classes = [PublicEndpoint]

    class AuthenticatedOnly(APIView):
        permission_classes = [IsAuthenticated]  # logged in, but no capability: any user could call it

    class WithCapability(APIView):
        permission_classes = [HasCapability("campaigns.view_own")]

    from django.urls import path

    patterns = [
        path("a", Undeclared.as_view()),
        path("b", OpenView.as_view()),
        path("c", SneakyAnonymous.as_view()),
        path("d", lambda request: None),
        path("e", AuthenticatedOnly.as_view()),
        path("ok", HealthLive.as_view()),
        path("ok2", WithCapability.as_view()),
    ]
    problems = find_violations(patterns)
    assert len(problems) == 5 and not any("ok:" in p or "ok2:" in p for p in problems)
    assert "declares no HasCapability" in next(
        p for p in problems if p.startswith("e/") or p.startswith("e:")
    )


def test_default_permission_is_deny_and_denies(client):
    from rest_framework.test import APIRequestFactory

    class Plain(APIView):
        def get(self, request):  # pragma: no cover
            ...

    from rest_framework.test import force_authenticate

    from apps.accounts.models import User

    anonymous = Plain.as_view()(APIRequestFactory().get("/x"))
    assert anonymous.status_code == 401  # nobody is let in; with an authenticator configured this is a 401
    request = APIRequestFactory().get("/x")
    force_authenticate(request, user=User(email="caller@example.com"))
    assert Plain.as_view()(request).status_code == 403  # authenticated but not permitted: the default deny


def test_health_views_are_in_allowlist():
    assert {HealthLive.__name__, HealthReady.__name__} <= ANONYMOUS_ALLOWLIST
