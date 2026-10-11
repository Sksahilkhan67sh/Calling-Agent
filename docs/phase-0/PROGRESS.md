# Phase 0 — Progress

| ID | Task | Status | Evidence path | Commit | Notes |
|---|---|---|---|---|---|
| P0-00 | Recon and scaffolding | DONE | docs/phase-0/ |  | branch phase-0/dograh-spike from local main (initial commit with docs); layout created |
| P0-01 | Inputs and environment check | DONE | docs/phase-0/PROGRESS.md |  | docs-only: 5 Dograh/test inputs missing -> PENDING_INPUT |
| P0-02 | Dograh docs research | TODO |  |  |  |
| P0-03 | Spike harness | TODO |  |  |  |
| P0-04 | V01 Webhook auth options and body signing | TODO |  |  |  |
| P0-05 | V02 Webhook payload template rendering | TODO |  |  |  |
| P0-06 | V03 Webhook delivery semantics and retry | TODO |  |  |  |
| P0-07 | V04 Get-run endpoint for verify-by-pull | TODO |  |  |  |
| P0-08 | V05 Run listing / filter by initial_context | TODO |  |  |  |
| P0-09 | V06 Final statuses and failure mapping | TODO |  |  |  |
| P0-10 | V07 Mid-call disconnect visibility | TODO |  |  |  |
| P0-11 | V08 Start-call idempotency and double-dial safety | TODO |  |  |  |
| P0-12 | V09 Reconnect via new run seeded with initial_context | TODO |  |  |  |
| P0-13 | V10 Artifacts: recordings and transcripts | TODO |  |  |  |
| P0-14 | V11 Agents API workflow sync | TODO |  |  |  |
| P0-15 | V12 Concurrency, rate limits, backpressure | TODO |  |  |  |
| P0-16 | V13 API key scope, rotation, network restriction | TODO |  |  |  |
| P0-17 | V14 Self-host production settings | TODO |  |  |  |
| P0-18 | Carrier shortlist | TODO |  |  |  |
| P0-19 | Status mapping consolidation | TODO |  |  |  |
| P0-20 | Webhook trust model decision | TODO |  |  |  |
| P0-21 | Doc patches | TODO |  |  |  |
| P0-22 | Phase 1+ handoff and open questions | TODO |  |  |  |
| P0-23 | Closeout and checkpoint | TODO |  |  |  |

## Environment readiness (presence only; no values recorded)

| Input | Present | Effect |
|---|---|---|
| REPO_URL / BASE_BRANCH / DOCS_PATH | yes (given in the run instructions) | none |
| DOGRAH_DEPLOYMENT | yes: self-hosted | none |
| CARRIER_IN_USE | yes: none-yet | carrier-dependent items stay docs-only |
| LIVE_TESTING | no | every live part is PENDING_LIVE |
| APPLY_DOC_PATCHES | no | design docs untouched; DOC-PATCHES.md only |
| MAX_TEST_CALLS / MAX_TEST_SPEND | 0 / 0 | zero calls permitted; the call guard refuses all dials |
| DOGRAH_BASE_URL | no | PENDING_INPUT |
| DOGRAH_API_KEY | no | PENDING_INPUT |
| DOGRAH_WORKFLOW_UUID | no | PENDING_INPUT |
| PUBLIC_WEBHOOK_URL | no | PENDING_INPUT |
| SPIKE_TEST_NUMBERS | no | PENDING_INPUT |
| Python | 3.12.3 | ok |
| pip | 24.0 | ok |
| gitleaks / detect-secrets | absent | grep rules in tools/secret_scan.sh are used |
| Dograh reachability | not checked | no DOGRAH_BASE_URL |


## Iteration log

- 2026-10-11T06:55Z P0-00 DONE — base commit + branch + layout. Next P0-01
- 2026-10-11T06:55Z P0-01 DONE — env table; no live inputs. Next P0-03 (harness built before P0-02 write-up so the hygiene gate exists; research for P0-02 is already done, only its write-up is deferred)
