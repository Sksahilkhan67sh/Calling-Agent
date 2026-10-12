"""Phase 1 URL conf: health probes and (dev only) API docs. Nothing else."""

from django.conf import settings
from django.urls import URLPattern, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.core.health import HealthLive, HealthReady


def build_urlpatterns(*, enable_api_docs: bool) -> list[URLPattern]:
    patterns = [
        path("healthz", HealthLive.as_view(), name="healthz"),
        path("readyz", HealthReady.as_view(), name="readyz"),
    ]
    if enable_api_docs:
        patterns += [
            path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
            path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
            path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
        ]
    return patterns


urlpatterns = build_urlpatterns(enable_api_docs=settings.ENABLE_API_DOCS)
