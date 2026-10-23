from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.views import health

urlpatterns = [
    path("healthz", health),
    path("webhooks/", include("apps.webhooks.urls")),
    path("v1/auth/", include("apps.accounts.urls")),
    path("v1/", include("apps.campaigns.urls")),
    path("v1/", include("apps.contacts.urls")),
    path("v1/", include("apps.suppression.urls")),
]
if settings.ADMIN_ENABLED:
    urlpatterns.append(path("admin/", admin.site.urls))
