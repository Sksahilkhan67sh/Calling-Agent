"""V04: poll get-run after a call ends to measure consistency lag; also probe an unknown id.

Usage: v04_get_run_lag.py WORKFLOW_ID RUN_ID [polls] [interval_s]
"""
import sys
import time

from _common import require_live, save_evidence, utcnow
from dograh_client import DograhClient


def snapshot(r) -> dict:
    b = r.body if isinstance(r.body, dict) else {}
    g = b.get("gathered_context") or {}
    return {"at": utcnow(), "http": r.status, "is_completed": b.get("is_completed"),
            "call_status": g.get("call_status"), "call_disposition": g.get("call_disposition"),
            "has_recording": bool(b.get("recording_url")), "has_transcript": bool(b.get("transcript_url")),
            "has_initial_context": bool(b.get("initial_context")), "cost_info_keys": sorted((b.get("cost_info") or {}))}


if __name__ == "__main__":
    require_live("V04", ["Complete one test call (V02) and note workflow_id and run_id",
                         "Run this script immediately when the webhook arrives; it polls every few seconds",
                         "Also run an in-progress poll (start before hang-up) and an unknown run id"])
    wf, run = int(sys.argv[1]), int(sys.argv[2])
    polls, gap = int(sys.argv[3]) if len(sys.argv) > 3 else 12, float(sys.argv[4]) if len(sys.argv) > 4 else 5
    c = DograhClient.from_env()
    rows = []
    for _ in range(polls):
        rows.append(snapshot(c.get_run(wf, run)))
        time.sleep(gap)
    unknown = c.get_run(wf, 2_000_000_000)
    save_evidence("V04", "poll_series.json", {"rows": rows, "unknown_run": {"http": unknown.status, "body": unknown.body}})
    print(*rows, sep="\n")
