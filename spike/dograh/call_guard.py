"""Hard safety gate for live calls: owned numbers only, call cap, masked ledger."""
import datetime
import os
import pathlib

from redact import mask_phone

LEDGER = pathlib.Path(__file__).resolve().parents[2] / "docs/phase-0/evidence/call-ledger.md"
HEADER = "| UTC time | number (masked) | run id | status | cost | purpose |\n|---|---|---|---|---|---|\n"


class CallRefused(Exception):
    pass


def _owned() -> set:
    return {n.strip() for n in os.environ.get("SPIKE_TEST_NUMBERS", "").split(",") if n.strip()}


def calls_made(ledger: pathlib.Path = LEDGER) -> int:
    if not ledger.exists():
        return 0
    return sum(1 for line in ledger.read_text().splitlines() if line.startswith("| 20"))


def authorize(number: str, purpose: str, ledger: pathlib.Path = LEDGER) -> None:
    """Raise CallRefused unless the call is allowed; otherwise reserve a ledger row."""
    if os.environ.get("LIVE_TESTING", "no").lower() != "yes":
        raise CallRefused("LIVE_TESTING is not 'yes'")
    if number not in _owned():
        raise CallRefused("number is not in SPIKE_TEST_NUMBERS")
    cap = int(os.environ.get("MAX_TEST_CALLS", "0"))
    if calls_made(ledger) >= cap:
        raise CallRefused(f"call cap reached ({cap})")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists():
        ledger.write_text("# Call ledger\n\n" + HEADER)
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with ledger.open("a") as f:
        f.write(f"| {now} | {mask_phone(number)} | pending | requested | n/a | {purpose} |\n")
