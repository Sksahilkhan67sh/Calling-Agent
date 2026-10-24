from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.contacts.importer import parse_numbers
from apps.contacts.models import Contact
from apps.core.crypto import encrypt, phone_hmac
from apps.core.permissions import ADMIN, MANAGER, SALES, user_roles
from apps.voice_runtime.client import DograhError

from .models import AgentConfig, Campaign, RetryPolicy
from .sync import render_workflow, sync_workflow, workflow_digest
from .serializers import (AgentConfigSerializer, CampaignCreateSerializer, CampaignSerializer,
                          CampaignStatusSerializer, RetryPolicySerializer)


def _campaigns(user):
    return Campaign.objects.for_user(user).annotate(contact_count=Count("contacts"))


def _filtered_by_status(request, qs, choices):
    if value := request.query_params.get("status"):
        if value not in choices:
            raise ValidationError({"status": f"Invalid status: {value}"})
        qs = qs.filter(status=value)
    return qs


class CampaignListCreateView(APIView):
    roles = {"GET": {ADMIN, MANAGER, SALES}, "POST": {ADMIN, MANAGER}}

    def get(self, request):
        qs = _filtered_by_status(request, _campaigns(request.user), Campaign.Status.values)
        return Response(CampaignSerializer(qs.order_by("-created_at"), many=True).data)

    def post(self, request):
        s = CampaignCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if ("retry_policy" in d or "agent_config" in d) and ADMIN not in user_roles(request.user):
            raise PermissionDenied("Only Admins can set retry policy or agent config.")
        numbers = parse_numbers(d["contact_file"])
        if not numbers:
            return Response({"code": "no_valid_contacts", "message": "No valid contacts found in the file."}, status=400)
        with transaction.atomic():
            campaign = Campaign.objects.create(owner=request.user, name=d["name"])
            RetryPolicy.objects.create(campaign=campaign, **d.get("retry_policy", {}))
            AgentConfig.objects.create(campaign=campaign, **d.get("agent_config", {}))
            Contact.objects.bulk_create(
                Contact(campaign=campaign, phone_encrypted=encrypt(n), phone_hmac=phone_hmac(n)) for n in numbers
            )
        return Response(CampaignSerializer(_campaigns(request.user).get(pk=campaign.pk)).data, status=201)


class CampaignDetailView(APIView):
    roles = {"GET": {ADMIN, MANAGER, SALES}, "PATCH": {ADMIN, MANAGER}}

    def get(self, request, campaign_id):
        campaign = get_object_or_404(_campaigns(request.user).select_related("agent_config"), pk=campaign_id)
        data = CampaignSerializer(campaign).data
        if ADMIN in user_roles(request.user):
            data["workflow_synced"] = campaign.workflow_synced_sha256 == workflow_digest(render_workflow(campaign))
        return Response(data)

    def patch(self, request, campaign_id):
        with transaction.atomic():
            campaign = get_object_or_404(Campaign.objects.for_user(request.user).select_for_update(), pk=campaign_id)
            s = CampaignStatusSerializer(campaign, data=request.data)
            s.is_valid(raise_exception=True)
            campaign.status = s.validated_data["status"]
            campaign.save(update_fields=["status"])
        return Response(CampaignSerializer(_campaigns(request.user).get(pk=campaign_id)).data)


class _CampaignConfigView(generics.RetrieveUpdateAPIView):
    # Writes to retry policy / agent config are Admin-only and audited with before/after
    http_method_names = ["get", "put", "head", "options"]
    roles = {"GET": {ADMIN, MANAGER}, "PUT": {ADMIN}}
    model = audit_name = None

    def get_object(self):
        visible = Campaign.objects.for_user(self.request.user)
        return get_object_or_404(self.model, campaign__in=visible, campaign_id=self.kwargs["campaign_id"])

    def perform_update(self, serializer):
        before = dict(self.get_serializer(serializer.instance).data)
        with transaction.atomic():
            serializer.save()
            record(f"{self.audit_name}.update", self.audit_name, serializer.instance.campaign_id,
                   actor=self.request.user, request=self.request, before=before, after=dict(serializer.data))


class RetryPolicyView(_CampaignConfigView):
    serializer_class = RetryPolicySerializer
    model, audit_name = RetryPolicy, "retry_policy"


class AgentConfigView(_CampaignConfigView):
    serializer_class = AgentConfigSerializer
    model, audit_name = AgentConfig, "agent_config"


class WorkflowSyncView(APIView):
    roles = {"POST": {ADMIN}}

    def post(self, request, campaign_id):
        campaign = get_object_or_404(Campaign.objects.for_user(request.user), pk=campaign_id)
        try:
            campaign = sync_workflow(campaign.pk, actor=request.user, request=request)
        except DograhError:
            return Response({"detail": "Dograh workflow sync failed"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"workflow_uuid": campaign.dograh_workflow_uuid})
