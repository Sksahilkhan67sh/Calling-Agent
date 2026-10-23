import datetime
import uuid

from django.conf import settings
from django.db import models

from apps.core.permissions import ADMIN, MANAGER, SALES, user_roles

NEVER_CONNECTED_REASONS = ("no_answer", "busy", "invalid_number", "rejected", "network_error", "provider_error")
MID_CALL_REASONS = ("technical_issue", "network_problem", "provider_error", "ai_error", "unknown", "customer_hangup")
ENTITY_FIELDS = ("interest_level", "objection", "follow_up_preference", "decision_maker_status", "free_text_feedback")


def default_never_connected_rules():
    return {"no_answer": True, "busy": True, "invalid_number": False, "rejected": False,
            "network_error": True, "provider_error": True}


def default_mid_call_rules():
    return {"technical_issue": True, "network_problem": True, "provider_error": True,
            "ai_error": True, "unknown": True, "customer_hangup": False}


def default_spacing():
    return [30, 600]


class CampaignQuerySet(models.QuerySet):
    def for_user(self, user):
        roles = user_roles(user)
        if roles & {ADMIN, SALES}:  # Sales is read-only and only reaches contact/final-output views
            return self
        return self.filter(owner=user) if MANAGER in roles else self.none()


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        ACTIVE = "active"
        PAUSED = "paused"
        COMPLETED = "completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="campaigns")
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    dograh_workflow_uuid = models.UUIDField(null=True, blank=True)
    workflow_synced_sha256 = models.CharField(max_length=64, blank=True)

    objects = CampaignQuerySet.as_manager()


class RetryPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name="retry_policy")
    max_retries = models.PositiveIntegerField(default=2)
    retry_spacing_seconds = models.JSONField(default=default_spacing)
    never_connected_rules = models.JSONField(default=default_never_connected_rules)
    mid_call_rules = models.JSONField(default=default_mid_call_rules)
    window_start = models.TimeField(default=datetime.time(10, 0))
    window_end = models.TimeField(default=datetime.time(18, 0))


class AgentConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name="agent_config")
    persona_tone = models.CharField(max_length=255, blank=True)
    script_skeleton = models.JSONField(default=list)
    required_entity_fields = models.JSONField(default=list)
    escalation_contact_method = models.CharField(max_length=255, blank=True)
    prompt_template_version = models.CharField(max_length=32, default="v1")
    model_config_uuid = models.UUIDField(null=True, blank=True)  # named Dograh model config; keys stay in Dograh
