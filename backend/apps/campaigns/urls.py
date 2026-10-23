from django.urls import path

from . import views

urlpatterns = [
    path("campaigns", views.CampaignListCreateView.as_view()),
    path("campaigns/<uuid:campaign_id>", views.CampaignDetailView.as_view()),
    path("campaigns/<uuid:campaign_id>/retry-policy", views.RetryPolicyView.as_view()),
    path("campaigns/<uuid:campaign_id>/agent-config", views.AgentConfigView.as_view()),
]
