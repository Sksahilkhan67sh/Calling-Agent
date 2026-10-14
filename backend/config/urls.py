"""URL conf: health probes, the authentication endpoints and (dev only) API docs."""

from django.conf import settings
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.core.health import HealthLive, HealthReady


def build_urlpatterns(*, enable_api_docs: bool) -> list[URLPattern | URLResolver]:
    patterns: list[URLPattern | URLResolver] = [
        path("healthz", HealthLive.as_view(), name="healthz"),
        path("readyz", HealthReady.as_view(), name="readyz"),
        path(f"{settings.API_VERSION_PREFIX}/auth/", include("apps.accounts.urls")),
    ]
    if enable_api_docs:
        patterns += [
            path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
            path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
            path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
        ]
    return patterns


urlpatterns = build_urlpatterns(enable_api_docs=settings.ENABLE_API_DOCS)
