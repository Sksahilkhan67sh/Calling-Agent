from django.urls import path

from .views import SuppressView

urlpatterns = [path("contacts/<uuid:contact_id>/suppress", SuppressView.as_view())]
