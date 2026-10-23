from rest_framework import serializers

from .models import (ENTITY_FIELDS, MID_CALL_REASONS, NEVER_CONNECTED_REASONS, AgentConfig, Campaign, RetryPolicy)

TRANSITIONS = {
    Campaign.Status.DRAFT: {Campaign.Status.ACTIVE},
    Campaign.Status.ACTIVE: {Campaign.Status.PAUSED, Campaign.Status.COMPLETED},
    Campaign.Status.PAUSED: {Campaign.Status.ACTIVE, Campaign.Status.COMPLETED},
    Campaign.Status.COMPLETED: set(),
}


class CampaignSerializer(serializers.ModelSerializer):
    contact_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Campaign
        fields = ["id", "name", "status", "contact_count", "created_at"]


class CampaignStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Campaign.Status.choices)

    def validate_status(self, new):
        current = self.instance.status
        if new != current and new not in TRANSITIONS[current]:
            raise serializers.ValidationError(f"Cannot change status from {current} to {new}.")
        return new


def _rules(allowed, value):
    if unknown := set(value) - set(allowed):
        raise serializers.ValidationError(f"Invalid rule keys: {sorted(unknown)}")
    return value


class RetryPolicySerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField(read_only=True)
    max_retries = serializers.IntegerField(min_value=0, required=False)
    retry_spacing_seconds = serializers.ListField(child=serializers.IntegerField(min_value=0), required=False)
    never_connected_rules = serializers.DictField(child=serializers.BooleanField(), required=False)
    mid_call_rules = serializers.DictField(child=serializers.BooleanField(), required=False)

    class Meta:
        model = RetryPolicy
        fields = ["id", "campaign_id", "max_retries", "retry_spacing_seconds", "never_connected_rules",
                  "mid_call_rules", "window_start", "window_end"]
        extra_kwargs = {"window_start": {"required": False}, "window_end": {"required": False}}

    def validate_never_connected_rules(self, value):
        return _rules(NEVER_CONNECTED_REASONS, value)  # technical_issue is mid-call only

    def validate_mid_call_rules(self, value):
        return _rules(MID_CALL_REASONS, value)

    def validate(self, attrs):
        cur = self.instance or RetryPolicy()
        merged = {f: attrs.get(f, getattr(cur, f)) for f in
                  ("max_retries", "retry_spacing_seconds", "window_start", "window_end")}
        if len(merged["retry_spacing_seconds"]) != merged["max_retries"]:
            raise serializers.ValidationError("retry_spacing_seconds must have exactly max_retries values.")
        if merged["window_start"] >= merged["window_end"]:
            raise serializers.ValidationError("window_start must be before window_end.")
        for f in ("never_connected_rules", "mid_call_rules"):
            if f in attrs:
                attrs[f] = {**getattr(cur, f), **attrs[f]}
        return attrs


class AgentConfigSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField(read_only=True)
    script_skeleton = serializers.ListField(child=serializers.CharField(), required=False)
    required_entity_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ENTITY_FIELDS), required=False
    )

    class Meta:
        model = AgentConfig
        fields = ["id", "campaign_id", "persona_tone", "script_skeleton", "required_entity_fields",
                  "escalation_contact_method", "prompt_template_version", "model_config_uuid"]
        read_only_fields = ["prompt_template_version"]


def _nested(serializer_class):
    def validate(self, value):
        s = serializer_class(data=value)
        s.is_valid(raise_exception=True)
        return s.validated_data

    return validate


class CampaignCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    contact_file = serializers.FileField()
    retry_policy = serializers.JSONField(required=False)  # multipart carries it as a JSON string
    agent_config = serializers.JSONField(required=False)

    validate_retry_policy = _nested(RetryPolicySerializer)
    validate_agent_config = _nested(AgentConfigSerializer)
