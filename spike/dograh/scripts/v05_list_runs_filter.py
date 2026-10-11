"""V05: can runs be found by initial_context.attempt_id? Server-side filter probe + client-side scan.

Usage: v05_list_runs_filter.py WORKFLOW_ID ATTEMPT_ID SINCE_ISO
"""
import sys

from _common import require_live, save_evidence
from dograh_client import DograhClient


def find_attempt(runs: list, attempt_id: str):
    return next((r for r in runs if (r.get("initial_context") or {}).get("attempt_id") == attempt_id), None)


def scan_window(client, workflow_id: int, attempt_id: str, since_iso: str, max_pages: int = 50):
    """Newest-first paging; stop at the first run older than `since_iso` (ISO strings sort correctly)."""
    pages = 0
    for page in range(1, max_pages + 1):
        r = client.list_runs(workflow_id, page=page, limit=100, sort_order="desc")
        runs = (r.body or {}).get("runs", []) if isinstance(r.body, dict) else []
        pages = page
        if (hit := find_attempt(runs, attempt_id)):
            return hit, pages
        if not runs or runs[-1]["created_at"] < since_iso:
            break
    return None, pages


if __name__ == "__main__":
    require_live("V05", ["Make 3+ test runs with distinct attempt_id values (V02/V08)",
                         "Probe: list with an unsupported initialContext filter; if the row count equals the unfiltered count it is ignored",
                         "Run the client-side scan and record pages needed and elapsed time"])
    wf, attempt, since = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    c = DograhClient.from_env()
    base = c.list_runs(wf, limit=100)
    probe = c.list_runs(wf, limit=100, filters=[{"attribute": "initialContext", "type": "text",
                                                 "value": {"key": "attempt_id", "value": attempt}}])
    hit, pages = scan_window(c, wf, attempt, since)
    save_evidence("V05", "probe.json", {
        "unfiltered_total": (base.body or {}).get("total_count"), "unsupported_filter_total": (probe.body or {}).get("total_count"),
        "client_scan_found": bool(hit), "pages_scanned": pages, "limit": 100})
    print("found:", bool(hit), "pages:", pages)
