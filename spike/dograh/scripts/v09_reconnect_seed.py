"""V09: seeded reconnect. build_seed_context is the proposed Memory payload shape (UNVERIFIED until live).

Usage: v09_reconnect_seed.py +E164NUMBER PREV_ATTEMPT_ID SUMMARY_TEXT
"""
import json
import os
import sys
import uuid

from _common import require_live, save_evidence
from dograh_client import DograhClient

MAX_SEED_BYTES = 8_000  # conservative working limit until Dograh's real limit is measured


def build_seed_context(attempt_id, campaign_id, contact_ref, prev_attempt_id, summary, topics=()):
    ctx = {"attempt_id": attempt_id, "campaign_id": campaign_id, "contact_ref": contact_ref,
           "is_reconnect": "true", "previous_attempt_id": prev_attempt_id,
           "previous_summary": summary, "previous_topics": ", ".join(topics)}
    if len(json.dumps(ctx).encode()) > MAX_SEED_BYTES:
        raise ValueError("seed context too large")
    return ctx  # flat string values: prompts reference {{previous_summary}} directly


if __name__ == "__main__":
    require_live("V09", ["Call 1: answer, discuss 2 topics, hang up mid-conversation",
                         "Build the summary, run this script for call 2 and read the transcript",
                         "Check whether the agent acknowledges the drop and continues, not restarts",
                         "Probe size: use the test-run endpoint or validation failures, not real calls, to find the limit"])
    number, prev, summary = sys.argv[1], sys.argv[2], sys.argv[3]
    ctx = build_seed_context(str(uuid.uuid4()), "spike-reconnect", "spike-contact-1", prev, summary)
    r = DograhClient.from_env().start_call(os.environ["DOGRAH_WORKFLOW_UUID"], number, ctx, "V09 reconnect")
    save_evidence("V09", "reconnect_trigger.json", {"http": r.status, "body": r.body, "seed_keys": sorted(ctx)})
    print(r.status, r.body)
