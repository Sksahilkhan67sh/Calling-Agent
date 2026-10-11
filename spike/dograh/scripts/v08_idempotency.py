"""V08: duplicate-trigger and timeout-outcome tests. Each trigger is a REAL call (guarded, counts toward the cap).

Usage: v08_idempotency.py duplicate|timeout +E164NUMBER
"""
import os
import sys
import uuid

from _common import require_live, save_evidence
from dograh_client import DograhClient

if __name__ == "__main__":
    require_live("V08", [
        "duplicate: send the same body twice (same attempt_id); count runs carrying that attempt_id afterwards (needs 2 calls of budget)",
        "timeout: trigger with a 0.2 s read timeout; if the API answers faster, put a delay proxy in front; afterwards list runs and check whether one exists",
        "Record codes for: bad number format, unknown workflow uuid, unpublished workflow, missing key, concurrency exceeded",
        "Rule to validate: after a timeout/5xx the attempt becomes 'unknown outcome -> reconcile', never an automatic redial"])
    mode, number = sys.argv[1], sys.argv[2]
    c, wf = DograhClient.from_env(), os.environ["DOGRAH_WORKFLOW_UUID"]
    ctx = {"attempt_id": str(uuid.uuid4()), "campaign_id": "spike-idem", "contact_ref": "spike-contact-1"}
    if mode == "duplicate":
        results = [c.start_call(wf, number, ctx, "V08 duplicate") for _ in range(2)]
    else:
        results = [c.start_call(wf, number, ctx, "V08 timeout", timeout_s=0.2)]
    save_evidence("V08", f"{mode}.json", {"attempt_id": ctx["attempt_id"],
                                          "results": [{"http": r.status, "error": r.error, "body": r.body} for r in results]})
    print([(r.status, r.error) for r in results], "attempt_id:", ctx["attempt_id"])
