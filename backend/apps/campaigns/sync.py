import hashlib
import json

from django.conf import settings
from django.db import transaction

from apps.audit.services import record
from apps.voice_runtime.client import DograhClient, DograhError

from .models import Campaign

# Fixed in code so editing agent_config free text cannot remove them (Dograh Integration §4.3)
CONSENT_OPENING = "This call may be recorded for quality and follow-up purposes — is that okay with you?"
OPT_OUT_HANDLING = ("If the contact asks not to be called again, confirm, set call_disposition to opt_out, "
                    "and end the call politely.")
WEBHOOK_PAYLOAD = {
    "attempt_id": "{{initial_context.attempt_id}}",
    "campaign_id": "{{initial_context.campaign_id}}",
    "run_id": "{{workflow_run_id}}",
    "call_status": "{{gathered_context.call_status}}",
    "call_disposition": "{{gathered_context.call_disposition}}",
    "duration_seconds": "{{cost_info.call_duration_seconds}}",
    "recording_url": "{{recording_url}}",
    "transcript_url": "{{transcript_url}}",
}


def render_workflow(campaign):
    cfg = campaign.agent_config
    # [verify] Dograh's workflow-definition schema is not in the docs; node/edge keys here are unconfirmed
    return {
        "name": f"campaign-{campaign.id}",
        "nodes": [
            {"type": "start", "name": "consent_opening", "prompt": CONSENT_OPENING},
            {"type": "agent", "name": "conversation",
             "prompt": {"persona_tone": cfg.persona_tone, "script": cfg.script_skeleton,
                        "escalation": cfg.escalation_contact_method, "template_version": cfg.prompt_template_version},
             "extract": cfg.required_entity_fields},
            {"type": "agent", "name": "opt_out", "prompt": OPT_OUT_HANDLING},
            {"type": "webhook", "name": "run_completed", "method": "POST", "payload": WEBHOOK_PAYLOAD,
             "url": f"{settings.PUBLIC_BASE_URL}/webhooks/dograh/run-completed",
             "retry_config": {"enabled": True}},  # [verify] retry_config shape not in docs
        ],
    }


def workflow_digest(definition):
    return hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()


def sync_workflow(campaign_id, *, actor, request, runtime=None):
    runtime, failure = runtime or DograhClient(), None
    with transaction.atomic():
        # Row lock keeps two syncs from both creating a workflow for the same campaign
        campaign = Campaign.objects.select_for_update(of=("self",)).select_related("agent_config").get(pk=campaign_id)
        definition = render_workflow(campaign)
        digest = workflow_digest(definition)
        before = {"workflow_uuid": str(campaign.dograh_workflow_uuid or ""), "definition_sha256": campaign.workflow_synced_sha256}
        try:
            campaign.dograh_workflow_uuid = runtime.push_workflow(campaign.dograh_workflow_uuid, definition)
            campaign.save(update_fields=["dograh_workflow_uuid"])  # kept even if publish fails, so a retry updates instead of creating
            runtime.publish_workflow(campaign.dograh_workflow_uuid)
            campaign.workflow_synced_sha256 = digest
            campaign.save(update_fields=["workflow_synced_sha256"])
            record("agent_config.sync", "campaign", campaign.id, actor=actor, request=request, before=before,
                   after={"workflow_uuid": str(campaign.dograh_workflow_uuid), "definition_sha256": digest})
        except DograhError as e:
            failure = e  # raised after commit so the saved workflow uuid is not rolled back
    if failure:
        raise failure
    return campaign
