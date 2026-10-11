# Dograh spike (throwaway)

Phase 0 verification code. Not imported by any product code. Everything here exists to turn the
`[verify]` items in the design docs into evidence.

## Safety rules (enforced in code)
- `call_guard.py` refuses any live call unless `LIVE_TESTING=yes`, the number is in `SPIKE_TEST_NUMBERS`,
  and the ledger count is below `MAX_TEST_CALLS`. With the Phase 0 settings (`MAX_TEST_CALLS=0`) nothing can dial.
- `dograh_client.py` never retries the start-call trigger, sets a timeout on every request, never logs headers.
- Evidence is written only after `redact.py` has masked numbers, secrets, JWTs and URL tokens.
  Raw captures are never saved; `docs/phase-0/evidence/**/raw/` is git-ignored as a second barrier.

## Setup
```
cd spike/dograh
pip install -r requirements.txt        # httpx, pytest
cp .env.example .env                   # fill in (git-ignored); then: set -a; . ./.env; set +a
python3 -m pytest -q                   # all tests run offline
tools/hygiene.sh                       # run before every commit
```

## Scripts (one per verify item, in `scripts/`)
| Script | Item | Needs live Dograh? |
|---|---|---|
| `v01_webhook_auth.py` | V01 signing / auth headers | analyses receiver captures |
| `v02_trigger_and_capture.py` | V02 payload rendering | yes (1 call) |
| `v03_retry_matrix.py` | V03 retry semantics | analyses receiver captures |
| `v04_get_run_lag.py` | V04 get-run + lag | yes |
| `v05_list_runs_filter.py` | V05 list/filter + client-side match | yes (read-only) |
| `v06_status_matrix.py` | V06/V07 status table | analyses captures |
| `v08_idempotency.py` | V08 | yes (calls) |
| `v09_reconnect_seed.py` | V09 | yes (2 calls) |
| `v10_artifacts.py` | V10 | yes |
| `v11_agents_sync.py` | V11 | yes (scratch agent) |
| `v12_concurrency.py` | V12 | formula offline; test needs calls |
| `v14_posture_check.py` | V14 | offline, reads a stack env file |
V07 and V13 are procedures in the verification report (nothing to automate safely).

Receiver: `python3 webhook_receiver.py --item V01 [--mode ok|fail500|fail_then_ok|slow] --port 8081`,
then expose it with a tunnel and set `PUBLIC_WEBHOOK_URL`.
Status: scripts that call Dograh are untested against a real instance (no instance available in Phase 0).
