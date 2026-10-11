Title: Phase 0 — Dograh verification spike (docs-only: evidence, decisions, doc patches)

## Summary
Docs-only Phase 0 (`LIVE_TESTING=no`). Dograh's public documentation (read 2026-10-11) was compared with our V3 design; the spike harness and per-item scripts were built and tested offline; every live check is written up as exact steps. **No call was placed and no Dograh instance was contacted.**
- Disproved: run listing cannot filter by an `initial_context` key (V05); documented fallback adopted.
- Confirmed-with-limits: no real-time disconnect hook (V07); artifact downloads redirect to a signed storage URL (V10); API keys are org-scoped (V13); self-host settings exist as documented (V14, not observed).
- Design-impacting findings: get-run needs the integer `workflow_id`; no publish or credential endpoint in the Agents API; `retry_config` absent from the webhook node schema; `call_status` is an ending reason, not the carrier vocabulary; `DEFAULT_ORG_CONCURRENCY_LIMIT` is documented for Campaigns only; Dograh stores customer numbers in runs.
- Unknown until live: V01–V04, V06, V08, V09, V11, V12 and parts of V10/V13/V14.

## Verification results
| Item | Result | Decision | Evidence |
|---|---|---|---|
| V01 | UNVERIFIED-NEEDS-LIVE | keep trust model | VERIFICATION-REPORT.md |
| V02 | UNVERIFIED-NEEDS-LIVE | tolerant parsing | same, fixtures/ (docs-derived) |
| V03 | UNVERIFIED-NEEDS-LIVE | reconciler primary | same |
| V04 | UNVERIFIED-NEEDS-LIVE | integer workflow_id; backoff provisional | same |
| V05 | NOT-SUPPORTED | window scan fallback | same |
| V06 | UNVERIFIED-NEEDS-LIVE | mapping v0.1 | STATUS-MAPPING.md |
| V07 | CONFIRMED-WITH-LIMITS | stay with run-ended | same |
| V08 | UNVERIFIED-NEEDS-LIVE | never redial on unknown | same |
| V09 | UNVERIFIED-NEEDS-LIVE | flat seed keys | same |
| V10 | CONFIRMED-WITH-LIMITS | allowlist API + storage host | artifact_download.py + tests |
| V11 | UNVERIFIED-NEEDS-LIVE | UI credential, publish guard | evidence/V11/generated_definition.json |
| V12 | UNVERIFIED-NEEDS-LIVE | own semaphore, formula | v12_concurrency.py |
| V13 | CONFIRMED-WITH-LIMITS | rotation runbook | same |
| V14 | CONFIRMED-WITH-LIMITS | posture checker | v14_posture_check.py |

## Decisions taken
Webhook trust model unchanged (WEBHOOK-TRUST-MODEL.md); status mapping v0.1-docs-only; list-runs fallback; carrier: none chosen, shortlist and vendor questions in CARRIER-SHORTLIST.md; effective concurrency: formula only (baseline peak ≈ 22 connected calls, derived); self-hosted per instruction.

## Doc patches
Applied: **no** (`APPLY_DOC_PATCHES=no`). DOC-PATCHES.md lists DP-01 to DP-22 (including the stale Webhook-Specification §1–§3 and Project-Milestones M3.2).

## Spike code
Throwaway under `spike/dograh/`, not imported by product code. How to run: `spike/dograh/README.md`. 34 offline tests. Scripts that call Dograh are untested against a real instance.

## Safety
Live calls made: 0 (cap 0). Spend: 0 (cap 0). No secrets, unredacted numbers or raw artifacts committed; secret scan output: `SECRET-SCAN OK`. The call guard refuses every dial under the current settings.

## Open items
OPEN-QUESTIONS.md: 16 items. Owner for live items: Sahil (needs the five missing inputs, `LIVE_TESTING=yes`, and a non-zero call cap).

## How to verify (reviewer checklist)
1. Read VERIFICATION-REPORT.md; check three entries against the docs URLs in DOGRAH-CONTRACT.md §1.
2. Run `spike/dograh/tools/secret_scan.sh` on the branch.
3. `cd spike/dograh && pip install -r requirements.txt && python3 -m pytest -q`.
4. Check DOC-PATCHES.md quotes against the design docs.

## Risks / rollback
No production code. Rollback = revert the merge commit. Risk: provisional numbers (backoff, reconciler ceiling, receipt retention) rest on docs, not observation.
