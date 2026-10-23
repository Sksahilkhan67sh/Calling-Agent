from django.urls import path

from . import views

urlpatterns = [
    path("campaigns/<uuid:campaign_id>/contacts", views.CampaignContactListView.as_view()),
    path("contacts/<uuid:contact_id>", views.ContactDetailView.as_view()),
]
