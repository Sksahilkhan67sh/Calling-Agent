"""The real auth endpoints next to the test app's views, for end-to-end session tests."""

from django.conf import settings
from django.urls import include, path

from tests.testapp.urls import urlpatterns as testapp_patterns

urlpatterns = [path(f"{settings.API_VERSION_PREFIX}/auth/", include("apps.accounts.urls")), *testapp_patterns]
