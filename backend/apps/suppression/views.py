from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contacts.models import Contact
from apps.contacts.serializers import SuppressionSerializer
from apps.core.permissions import ADMIN

from .models import Suppression
from .services import suppress


class SuppressInput(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class SuppressView(APIView):
    roles = {"POST": {ADMIN}}

    def post(self, request, contact_id):
        contact = get_object_or_404(Contact.objects.for_user(request.user), pk=contact_id)
        s = SuppressInput(data=request.data)
        s.is_valid(raise_exception=True)
        suppression, created = suppress(
            contact, s.validated_data["reason"], Suppression.Source.MANUAL_API, actor=request.user, request=request
        )
        return Response(SuppressionSerializer(suppression).data, status=201 if created else 200)
