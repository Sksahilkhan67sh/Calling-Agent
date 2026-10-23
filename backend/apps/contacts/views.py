from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.campaigns.models import Campaign
from apps.core.permissions import ADMIN, MANAGER, SALES

from .models import Contact
from .serializers import ContactDetailSerializer, ContactSerializer


class ContactPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({"total": self.page.paginator.count, "page": self.page.number, "items": data})


class CampaignContactListView(generics.ListAPIView):
    roles = {"GET": {ADMIN, MANAGER, SALES}}
    serializer_class = ContactSerializer
    pagination_class = ContactPagination

    def get_queryset(self):
        campaign = get_object_or_404(Campaign.objects.for_user(self.request.user), pk=self.kwargs["campaign_id"])
        qs = campaign.contacts.order_by("created_at", "id")
        if value := self.request.query_params.get("status"):
            if value not in Contact.Status.values:
                raise ValidationError({"status": f"Invalid status: {value}"})
            qs = qs.filter(status=value)
        return qs


class ContactDetailView(generics.RetrieveAPIView):
    roles = {"GET": {ADMIN, MANAGER, SALES}}
    serializer_class = ContactDetailSerializer
    lookup_url_kwarg = "contact_id"

    def get_queryset(self):
        return Contact.objects.for_user(self.request.user).select_related("suppression")
