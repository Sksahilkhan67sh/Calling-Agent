# Phase 0 — Progress

| ID | Task | Status | Evidence path | Commit | Notes |
|---|---|---|---|---|---|
| P0-00 | Recon and scaffolding | DONE | docs/phase-0/ |  | branch phase-0/dograh-spike from local main (initial commit with docs); layout created |
| P0-01 | Inputs and environment check | DONE | docs/phase-0/PROGRESS.md |  | docs-only: 5 Dograh/test inputs missing -> PENDING_INPUT |
| P0-02 | Dograh docs research | DONE | docs/phase-0/DOGRAH-CONTRACT.md |  | docs-only; 17 docs-vs-design differences (D01-D17); carrier pages, create-from-definition, API-key create pages not read |
| P0-03 | Spike harness | DONE | spike/dograh/ |  | 26 pytest green; scan catches planted token; receiver echoes redacted capture; scripts v01..v14 follow in their tasks |
| P0-04 | V01 Webhook auth options and body signing | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v01; evidence/V01 |  | docs done; owner Sahil; needs DOGRAH_* + PUBLIC_WEBHOOK_URL + LIVE_TESTING |
| P0-05 | V02 Webhook payload template rendering | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v02 |  | docs done; fixture is docs-derived |
| P0-06 | V03 Webhook delivery semantics and retry | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v03 |  | retry_config absent from node schema |
| P0-07 | V04 Get-run endpoint for verify-by-pull | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v04 |  | field table from docs; lag needs live |
| P0-08 | V05 Run listing / filter by initial_context | DONE | docs/phase-0/VERIFICATION-REPORT.md#v05 |  | NOT-SUPPORTED per docs; window-scan fallback adopted |
| P0-09 | V06 Final statuses and failure mapping | PENDING_LIVE | docs/phase-0/STATUS-MAPPING.md |  | mapping v0.1 provisional |
| P0-10 | V07 Mid-call disconnect visibility | DONE | docs/phase-0/VERIFICATION-REPORT.md#v07 |  | no real-time hook (docs); classification live check under V06 steps |
| P0-11 | V08 Start-call idempotency and double-dial safety | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v08 |  | needs real calls |
| P0-12 | V09 Reconnect via new run seeded with initial_context | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v09 |  | needs 2 real calls |
| P0-13 | V10 Artifacts: recordings and transcripts | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v10 |  | docs + downloader tests done; expiry/format need live |
| P0-14 | V11 Agents API workflow sync | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v11; evidence/V11 |  | no publish/credential endpoint documented; design change flagged |
| P0-15 | V12 Concurrency, rate limits, backpressure | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v12 |  | formula done; limit behaviour needs live |
| P0-16 | V13 API key scope, rotation, network restriction | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v13 |  | docs done; rotation test needs live |
| P0-17 | V14 Self-host production settings | PENDING_LIVE | docs/phase-0/VERIFICATION-REPORT.md#v14 |  | settings documented; instance not available |
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
- 2026-10-11T06:57Z P0-03 DONE — harness + 26 tests. Next P0-02 write-up
- 2026-10-11T06:58Z P0-02 DONE — contract + diff table. Next P0-04 (V01)
- 2026-10-11T07:02Z P0-04..P0-17 recorded in VERIFICATION-REPORT (V05 DONE, V07 DONE, rest PENDING_LIVE with live steps). Next P0-18 and mapping docs
