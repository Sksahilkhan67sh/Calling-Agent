from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.views import health

urlpatterns = [
    path("healthz", health),
    path("v1/auth/", include("apps.accounts.urls")),
]
if settings.ADMIN_ENABLED:
    urlpatterns.append(path("admin/", admin.site.urls))
