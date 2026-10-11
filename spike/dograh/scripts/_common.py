"""Shared helpers for the per-item spike scripts."""
import datetime
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from redact import redact_obj  # noqa: E402

EVIDENCE = pathlib.Path(__file__).resolve().parents[3] / "docs/phase-0/evidence"


def save_evidence(item: str, name: str, obj) -> pathlib.Path:
    """Write redacted JSON evidence. Anything that reaches disk passes through redact_obj."""
    path = EVIDENCE / item / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_obj(obj), indent=2, sort_keys=True))
    return path


def load_captures(item: str, evidence: pathlib.Path = EVIDENCE) -> list:
    """Receiver captures (numbered .json files) for an item, in arrival order."""
    return [json.loads(p.read_text()) for p in sorted((evidence / item).glob("[0-9][0-9][0-9]_*.json"))]


def body_json(capture: dict) -> dict:
    try:
        return json.loads(capture.get("body", ""))
    except ValueError:
        return {}


def require_live(item: str, steps: list) -> None:
    """Exit cleanly with PENDING_LIVE instructions unless live testing is on and inputs exist."""
    missing = [v for v in ("DOGRAH_BASE_URL", "DOGRAH_API_KEY", "DOGRAH_WORKFLOW_UUID") if not os.environ.get(v)]
    if os.environ.get("LIVE_TESTING", "no").lower() != "yes" or missing:
        print(f"{item}: PENDING_LIVE (LIVE_TESTING!=yes or missing inputs: {', '.join(missing) or 'none'})")
        for i, s in enumerate(steps, 1):
            print(f"  {i}. {s}")
        sys.exit(0)


def utcnow() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
