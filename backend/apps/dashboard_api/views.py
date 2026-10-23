from django.conf import settings
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import Analysis, FinalOutput
from apps.audit.services import record
from apps.calls.models import CallAttempt, DisconnectEvent, Transcript
from apps.campaigns.models import Campaign
from apps.contacts.models import Contact
from apps.core.permissions import ADMIN, MANAGER, SALES
from apps.recovery.services import s3

from .serializers import (CallAttemptSerializer, DisconnectEventSerializer, FinalOutputSerializer,
                          TranscriptSerializer)

STAFF = {ADMIN, MANAGER}  # Sales gets final outputs and contact views only, never raw recordings/transcripts


class ContactFinalOutputView(generics.RetrieveAPIView):
    roles = {"GET": {ADMIN, MANAGER, SALES}}
    serializer_class = FinalOutputSerializer

    def get_object(self):
        contacts = Contact.objects.for_user(self.request.user)
        return get_object_or_404(FinalOutput.objects.select_related("transcript_ref", "recording_ref"),
                                 contact__in=contacts, contact_id=self.kwargs["contact_id"])


def _attempts(user):
    return CallAttempt.objects.filter(contact__campaign__in=Campaign.objects.for_user(user))


class _AttemptView(generics.RetrieveAPIView):
    roles = {"GET": STAFF}

    def get_attempt(self):
        return get_object_or_404(_attempts(self.request.user), pk=self.kwargs["attempt_id"])


class AttemptDetailView(_AttemptView):
    serializer_class = CallAttemptSerializer

    def get_object(self):
        return self.get_attempt()


class TranscriptView(_AttemptView):
    serializer_class = TranscriptSerializer

    def get_object(self):
        attempt = self.get_attempt()
        transcript = get_object_or_404(Transcript, attempt=attempt)
        record("transcript.access", "call_attempt", attempt.pk, actor=self.request.user, request=self.request)
        return transcript


class RecordingView(_AttemptView):
    def get(self, request, attempt_id):
        attempt = self.get_attempt()
        ref = getattr(attempt, "recording", None)
        if ref is None:
            return Response({"detail": "Not found."}, status=404)
        url = s3().generate_presigned_url(
            "get_object", Params={"Bucket": settings.OBJECT_STORAGE_BUCKET, "Key": ref.storage_path},
            ExpiresIn=settings.RECORDING_URL_TTL_SECONDS)
        record("recording.access", "call_attempt", attempt.pk, actor=request.user, request=request)
        return Response({"attempt_id": attempt.pk, "url": url, "duration_seconds": ref.duration_seconds})


class DisconnectEventsView(_AttemptView):
    def get(self, request, attempt_id):
        attempt = self.get_attempt()
        return Response(DisconnectEventSerializer(attempt.disconnect_events.order_by("occurred_at"), many=True).data)


class CampaignAnalyticsView(APIView):
    roles = {"GET": STAFF}

    def get(self, request, campaign_id):
        campaign = get_object_or_404(Campaign.objects.for_user(request.user), pk=campaign_id)
        A = CallAttempt.State
        connected = CallAttempt.objects.filter(contact__campaign=campaign, state__in=[A.CONNECTED, A.ENDED_NORMALLY, A.DROPPED_MID_CALL])
        events = DisconnectEvent.objects.filter(attempt__contact__campaign=campaign)
        analyses = Analysis.objects.filter(attempt__contact__campaign=campaign)
        n_connected, n_events = connected.count(), events.count()
        reconnected = events.filter(attempt__reconnects__state__in=[A.CONNECTED, A.ENDED_NORMALLY, A.DROPPED_MID_CALL]).distinct().count()
        temps = dict(analyses.values_list("temperature_tag").annotate(n=Count("id")))
        return Response({
            "campaign_id": campaign.pk,
            "status_counts": dict(campaign.contacts.values_list("status").annotate(n=Count("id"))),
            "average_lead_score": analyses.aggregate(a=Avg("lead_score"))["a"],
            "temperature_distribution": {t: temps.get(t, 0) for t in ("Hot", "Warm", "Cold")},
            "disconnect_rate": connected.filter(state=A.DROPPED_MID_CALL).count() / n_connected if n_connected else None,
            "reconnect_success_rate": reconnected / n_events if n_events else None,
        })
