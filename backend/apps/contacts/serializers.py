from rest_framework import serializers

from apps.suppression.models import Suppression

from .models import Contact


class SuppressionSerializer(serializers.ModelSerializer):
    contact_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Suppression
        fields = ["contact_id", "reason", "source", "requested_at"]


class ContactSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField(read_only=True)
    phone_number = serializers.CharField(read_only=True)

    class Meta:
        model = Contact
        fields = ["id", "campaign_id", "phone_number", "status", "attempt_count", "created_at"]


class ContactDetailSerializer(ContactSerializer):
    suppression = SuppressionSerializer(read_only=True)

    class Meta(ContactSerializer.Meta):
        fields = ContactSerializer.Meta.fields + ["suppression"]
