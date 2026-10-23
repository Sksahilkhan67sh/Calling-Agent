from django.urls import path

from . import views

urlpatterns = [
    path("contacts/<uuid:contact_id>/final-output", views.ContactFinalOutputView.as_view()),
    path("call-attempts/<uuid:attempt_id>", views.AttemptDetailView.as_view()),
    path("call-attempts/<uuid:attempt_id>/transcript", views.TranscriptView.as_view()),
    path("call-attempts/<uuid:attempt_id>/recording", views.RecordingView.as_view()),
    path("call-attempts/<uuid:attempt_id>/disconnect-events", views.DisconnectEventsView.as_view()),
    path("dashboard/campaigns/<uuid:campaign_id>/analytics", views.CampaignAnalyticsView.as_view()),
]
