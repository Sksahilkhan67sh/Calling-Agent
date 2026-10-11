"""V11: render agent_config into a Dograh workflow definition; optionally create + validate a SCRATCH agent.

Usage: v11_agents_sync.py [--apply]   (--apply only creates agents named P0-SPIKE-*)
"""
import os
import sys
import uuid

from _common import require_live, save_evidence
from dograh_client import DograhClient


def build_definition(agent_config: dict, webhook_url: str, credential_uuid: str | None) -> dict:
    """Consent opening and opt-out handling are fixed by code, not by agent_config free text."""
    n = lambda: str(uuid.uuid4())
    start, talk, optout, end, hook = n(), n(), n(), n(), n()
    consent = ("Hello, this is an automated assistant calling on behalf of "
               f"{agent_config['company']}. This is a test call and may be recorded. Is now a good time?")
    nodes = [
        {"id": start, "type": "startCall", "position": {"x": 0, "y": 0},
         "data": {"name": "Consent opening", "prompt": consent, "wait_for_user_response": True,
                  "detect_voicemail": True}},
        {"id": talk, "type": "agentNode", "position": {"x": 300, "y": 0},
         "data": {"name": "Conversation", "prompt": agent_config["script_prompt"], "allow_interrupt": True}},
        {"id": optout, "type": "endCall", "position": {"x": 300, "y": 200},
         "data": {"name": "Opt-out", "prompt": "Confirm you will not call again, apologise briefly, say goodbye."}},
        {"id": end, "type": "endCall", "position": {"x": 600, "y": 0},
         "data": {"name": "End", "prompt": "Thank the person and say goodbye."}},
        {"id": hook, "type": "webhook", "position": {"x": 900, "y": 0},
         "data": {"name": "Run completed", "enabled": True, "http_method": "POST", "endpoint_url": webhook_url,
                  "credential_uuid": credential_uuid,
                  "payload_template": {"attempt_id": "{{initial_context.attempt_id}}",
                                       "campaign_id": "{{initial_context.campaign_id}}",
                                       "run_id": "{{workflow_run_id}}", "workflow_id": "{{workflow_id}}",
                                       "call_status": "{{gathered_context.call_status}}",
                                       "call_disposition": "{{gathered_context.call_disposition}}",
                                       "duration_seconds": "{{cost_info.call_duration_seconds}}",
                                       "recording_url": "{{recording_url}}", "transcript_url": "{{transcript_url}}"}}}]
    edge = lambda a, b, cond: {"id": n(), "source": a, "target": b, "data": {"label": cond[:30], "condition": cond}}
    edges = [edge(start, talk, "The person agrees to continue the call"),
             edge(start, optout, "The person asks not to be called again or declines"),
             edge(talk, end, "The conversation goal is complete or the person wants to finish"),
             edge(talk, optout, "The person asks not to be called again")]
    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    cfg = {"company": "ExampleCo", "script_prompt": "Ask two short qualifying questions, then finish."}
    definition = build_definition(cfg, os.environ.get("PUBLIC_WEBHOOK_URL", "https://example.invalid/webhooks/dograh/run-completed"),
                                  os.environ.get("DOGRAH_WEBHOOK_CREDENTIAL_UUID"))
    save_evidence("V11", "generated_definition.json", definition)
    if "--apply" not in sys.argv:
        print("dry run: definition saved; add --apply for a scratch agent")
        sys.exit(0)
    require_live("V11", ["Create a scratch agent (name P0-SPIKE-*) from the generated definition",
                         "Validate it, update it once, then find out in the UI/API how a version becomes published",
                         "Trigger it by its Agent UUID with the V02 script"])
    c = DograhClient.from_env()
    created = c.create_agent("P0-SPIKE-" + uuid.uuid4().hex[:6], definition)
    wid = (created.body or {}).get("id") if isinstance(created.body, dict) else None
    validated = c.validate_agent(wid) if wid else None
    save_evidence("V11", "create_and_validate.json", {"create_http": created.status, "create_body": created.body,
                                                      "validate_http": validated and validated.status,
                                                      "validate_body": validated and validated.body})
    print(created.status, validated and validated.status)
