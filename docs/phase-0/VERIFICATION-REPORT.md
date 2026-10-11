# Phase 0 — Verification report (docs-only run)

Run mode: `LIVE_TESTING=no`, `MAX_TEST_CALLS=0`. Every entry below rests on **documentation read on 2026-10-11** (index in `DOGRAH-CONTRACT.md` §1) and on offline tests of our own code. **No call was placed and no Dograh instance was contacted.**
"Result" follows the plan's vocabulary. A documentation reading may support `CONFIRMED`/`NOT-SUPPORTED` only where the docs are explicit; where behaviour has to be observed the result is `UNVERIFIED-NEEDS-LIVE` and the exact live steps are listed (scripts live in `spike/dograh/scripts/`, receiver in `spike/dograh/webhook_receiver.py`).

| Item | Result | Decision / fallback | Evidence |
|---|---|---|---|
| V01 Webhook auth and signing | UNVERIFIED-NEEDS-LIVE (docs: no signing documented) | Keep shared secret + network restriction + verify-by-pull + receipt + reconciler | DOGRAH-CONTRACT §3 |
| V02 Template rendering | UNVERIFIED-NEEDS-LIVE | Template from Dograh-Integration §4.2 plus `workflow_id`; parse types defensively | DOGRAH-CONTRACT §3, fixtures/ |
| V03 Delivery and retry | UNVERIFIED-NEEDS-LIVE | Assume at-most-once delivery; reconciler is the primary recovery path | DOGRAH-CONTRACT §3, §10 D04 |
| V04 Get-run for verify-by-pull | UNVERIFIED-NEEDS-LIVE (field table from docs) | Pull needs integer `workflow_id`; bounded backoff provisional | DOGRAH-CONTRACT §2.2 |
| V05 List/filter by `initial_context` | **NOT-SUPPORTED** (docs explicit) | Time-window scan with client-side match; `DIAL_REQUESTED` row first | DOGRAH-CONTRACT §2.3; `v05_list_runs_filter.py` tested offline |
| V06 Final statuses | UNVERIFIED-NEEDS-LIVE | Provisional mapping v0.1, unknown → `provider_error` + alert | STATUS-MAPPING.md |
| V07 Mid-call visibility | CONFIRMED-WITH-LIMITS | Stay with run-ended notification; no real-time hook exists | DOGRAH-CONTRACT §4 |
| V08 Trigger idempotency | UNVERIFIED-NEEDS-LIVE | Rule "unknown outcome → reconcile, never redial" kept | DOGRAH-CONTRACT §7 |
| V09 Seeded reconnect | UNVERIFIED-NEEDS-LIVE | Flat string seed keys proposed; working limit 8 KB | `v09_reconnect_seed.py` |
| V10 Artifacts | CONFIRMED-WITH-LIMITS | Allowlist API host + storage host; one re-validated redirect | `artifact_download.py` + 6 negative/positive tests |
| V11 Agents API sync | UNVERIFIED-NEEDS-LIVE (design change flagged) | Credential created once in UI; publish step unknown | `evidence/V11/generated_definition.json` (generated, not yet accepted by Dograh) |
| V12 Concurrency | UNVERIFIED-NEEDS-LIVE | Django enforces its own ceiling; formula in script | `v12_concurrency.py` |
| V13 API keys | CONFIRMED-WITH-LIMITS | Rotation by create → switch → archive; key-management auth unknown | DOGRAH-CONTRACT §2 |
| V14 Self-host posture | CONFIRMED-WITH-LIMITS (settings documented, none observed) | Checklist + `v14_posture_check.py` for the running stack | DOGRAH-CONTRACT §8 |

---

### V01 — Webhook authentication options and body signing
- Question: can the webhook node sign the body or send a signed timestamp; which credential types exist?
- Why it matters: Webhook-Specification §4A, Security-Architecture §2 row 4.
- Method: docs; live capture pending.
- Evidence: docs `/developer/webhooks`, `/voice-agent/webhook` (2026-10-11).
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: credential types `NONE`, `API_KEY` (custom header), `BEARER_TOKEN`, `BASIC_AUTH`, `CUSTOM_HEADER`; node also has `custom_headers`; no HMAC, signature or signed-timestamp feature appears anywhere in the node schema or payload variables; `call_time` is the run creation time. Header name/format, extra headers (user agent, request id), source IPs and TLS behaviour are not documented.
- Design impact: none (the design already assumes no signing).
- Decision / fallback: keep the model in `WEBHOOK-TRUST-MODEL.md`. Change only if the live capture shows a signature or timestamp header.
- Doc patches: DP-02.
- Tests to add: TC-DG.01–03 already cover the secret; add TC-DG.13 "unexpected extra headers are ignored".
- **Live steps:** (1) in the Dograh UI create a credential type `API_KEY` with header `X-Dograh-Webhook-Secret` and a random 32-byte value; (2) set the workflow webhook node `endpoint_url` to `PUBLIC_WEBHOOK_URL`, template from Dograh-Integration §4.2; (3) `python3 webhook_receiver.py --item V01` behind the tunnel; (4) one test call via `scripts/v02_trigger_and_capture.py`; (5) `python3 scripts/v01_webhook_auth.py V01` and read the VERDICT line; record header names, the secret's `len=… chars=…` shape and whether any signing-like header exists.

### V02 — Webhook payload template rendering
- Question: do the correlation variables render; types of empty values; payload size limit.
- Why it matters: Dograh-Integration §4.2.
- Method: docs; live pending.
- Evidence: `/developer/webhooks`, `/core-concepts/context-and-variables`; `spike/dograh/fixtures/webhook_run_completed.docs-derived.json` (derived from docs, **not observed**).
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts (docs): variable types are `workflow_run_id` integer, `workflow_id` integer, `cost_info.call_duration_seconds` number, `recording_url`/`transcript_url` string or null, `campaign_id` integer or null. Templates are JSON where values are written as strings (`"{{x}}"`), so whether numbers arrive as strings and how null/missing render is unknown. A top-level `call_disposition` is added if absent. No payload size limit documented.
- Design impact: doc patch (add `workflow_id`; note `campaign_id` clash).
- Decision / fallback: receiver must accept numbers as strings or numbers, and `None`/empty/`"None"` for missing values; schema validation tolerant on types, strict on presence of `attempt_id` and `run_id`.
- Doc patches: DP-03.
- Tests to add: TC-WH.08 "numeric fields as strings accepted", TC-WH.09 "empty recording_url accepted".
- **Live steps:** run V01 steps with `initial_context` from `v02_trigger_and_capture.py`; then repeat with an unanswered call (never connected) and a call hung up early; copy the redacted captures from `evidence/V02/` into `spike/dograh/fixtures/` (replace the docs-derived fixture).

### V03 — Webhook delivery semantics and retry
- Question: does Dograh retry non-200; what does `retry_config` accept; duplicates; timeout; redirects.
- Method: docs; live pending (receiver modes `fail_then_ok`, `fail500`, `slow`).
- Evidence: `/developer/webhooks` (non-200 logged, not retried by default; "configure `retry_config` to change this"; reply within 30 s; retries may duplicate).
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: `retry_config` is mentioned on one page and is **absent from the workflow-definition node schema**; its fields (count, backoff) are undocumented.
- Design impact: design change possible — if `retry_config` does not exist, webhook loss is only recovered by the reconciler.
- Decision / fallback: do not depend on retries. Respond 2xx within 2 s (receipt written, work queued). Response-code policy in WEBHOOK-TRUST-MODEL §4.
- Doc patches: DP-04, DP-05.
- Tests to add: TC-DG.05 (exists), TC-WH.10 "retry delivery with identical body is idempotent".
- **Live steps:** (1) `webhook_receiver.py --item V03 --mode fail_then_ok --fail-count 1`, one call; (2) `--mode fail500`, one call; (3) `--mode slow --slow-seconds 35`, one call; (4) `python3 scripts/v03_retry_matrix.py V03` for attempts, intervals, header/body identity; (5) try adding `retry_config` to the node via UI/API and record accepted fields; (6) answer with a 302 to see whether redirects are followed.

### V04 — Get-run endpoint for verify-by-pull
- Question: does get-run return everything verify-by-pull and the reconciler need; behaviour for in-progress, never-connected, unknown id; lag after the webhook.
- Method: docs for the field table; live for lag.
- Evidence: `/api-reference/runs/get-run`.
- Result: UNVERIFIED-NEEDS-LIVE (field table from docs).
- Observed facts (docs): path `GET /api/v1/workflow/{workflow_id}/runs/{run_id}`; both ids are **integers**; returns `id`, `workflow_id`, `is_completed`, `initial_context`, `gathered_context` (`call_status`, `call_disposition`, `mapped_call_disposition`), `cost_info`, `usage_info`, `recording_url`, `transcript_url`, `public_access_token`, `created_at`, `call_type`, `logs`, `annotations`. No `status` field and no explicit end timestamp. Unknown id → 404 documented; the in-progress shape is not.
- Design impact: doc patch (workflow id required; no run `status` field).
- Decision / fallback: verify-by-pull uses the integer `workflow_id` stored on our side for the attempt's agent, never the one in the webhook body. Provisional backoff in WEBHOOK-TRUST-MODEL §3.
- Doc patches: DP-01.
- Tests to add: TC-DG.04 (exists); TC-DG.14 "pulled run not yet complete → retried then handed to reconciler".
- **Live steps:** `python3 scripts/v04_get_run_lag.py WORKFLOW_ID RUN_ID 24 5` started when the call begins and kept running past the webhook arrival; again after a no-answer call; unknown id is probed by the script. Read `evidence/V04/poll_series.json` for the first poll where `is_completed` is true relative to webhook arrival.

### V05 — Run listing and filtering by `initial_context`
- Question: can runs be listed and filtered by an `initial_context` value, time, workflow, status?
- Method: docs (explicit); live probe of the "ignored filter" behaviour pending.
- Evidence: `/api-reference/runs/list-runs`, `/api-reference/agents/runs/list`.
- Result: **NOT-SUPPORTED** (documented filters listed in DOGRAH-CONTRACT §2.3; none targets an arbitrary `initial_context` key).
- Observed facts: org endpoint `GET /api/v1/organizations/usage/runs` supports `start_date`/`end_date` (on `created_at`), `page`, `limit` ≤ 100, `sort_by` duration|created_at, `sort_order`, and filters `runId`, `workflowId`, `campaignId`, `callerNumber`, `calledNumber` (substring, number PII), `dispositionCode`, `duration`, `callDirection`, `callChannel`. **Unknown filter attributes are silently ignored.** Rows include `initial_context`, so client-side matching on `attempt_id` works. The per-workflow list returns full run objects (no filter schema documented). No rate limits documented.
- Design impact: doc patch; design unchanged (the fallback already exists).
- Decision / fallback adopted: (1) write `DIAL_REQUESTED` before the trigger; (2) after an unknown outcome the reconciler lists the org endpoint with `start_date = dial_requested_at − 60 s`, `workflowId` filter, `limit=100`, newest first, and matches `initial_context.attempt_id` client-side; (3) cost = ⌈runs created since that time ÷ 100⌉ requests per unresolved attempt; at the baseline of about 100 000 contacts/month spread over 8 h × 22 days (≈ 9.5 dials/min) a 10-minute window is about 95 runs, so one page. Several unresolved attempts share one scan. (4) Never filter by phone number. (5) A guard test: if the unsupported-filter probe returns the same total as the unfiltered list, the filter is ignored (the script records both totals).
- Doc patches: DP-06.
- Tests to add: TC-DG.06 (exists) plus TC-DG.15 "reconciler finds a run by window scan".
- **Live steps:** make ≥ 3 test runs with distinct `attempt_id`s; `python3 scripts/v05_list_runs_filter.py WORKFLOW_ID ATTEMPT_ID SINCE_ISO`; read `evidence/V05/probe.json` (`unfiltered_total` vs `unsupported_filter_total`, `pages_scanned`).

### V06 — Final statuses and failure mapping
- Question: which statuses/dispositions appear for answered, busy, no-answer, rejected, invalid number, carrier failure, network failure, canceled, AI error.
- Method: docs; live pending (only owned numbers; no random numbers).
- Evidence: `/integrations/telephony/webhooks`, `/developer/call-dispositions`; `STATUS-MAPPING.md`.
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: carrier callbacks normalise to initiated, ringing, in-progress, answered, completed, busy, no-answer, canceled, failed, error (unknown statuses pass through). The run field `gathered_context.call_status` is "the observed reason the call ended" (example `user_hangup`), `call_disposition` falls back to it when business-outcome extraction is off. How the normalised carrier statuses reach the run or webhook is undocumented.
- Design impact: doc patch (Dograh-Integration §5.2 must not claim the final status is the carrier vocabulary).
- Decision / fallback: `STATUS-MAPPING.md` v0.1 with default `provider_error` + alert for unknown never-connected statuses and `unknown` for mid-call.
- Doc patches: DP-07.
- Tests to add: TC-DG.11 (exists, extend) and TC-DG.16 "every observed (call_status) value has a mapping row".
- **Live steps:** with owned numbers: answered-and-completed, answered-then-hang-up, decline, unanswered, phone switched off or in airplane mode (if the number is yours), agent-ended call. For each save the webhook capture (V02 receiver) and the get-run snapshot (V04 script). Tabulate with `python3 scripts/v06_status_matrix.py V06`. Ask the carrier (and Dograh) the vendor questions in STATUS-MAPPING §5 for invalid numbers.

### V07 — Mid-call disconnect visibility
- Question: what a dropped connected call looks like in the run result; any real-time hook.
- Method: docs; live pending.
- Evidence: `/configurations/call-events`, `/integrations/telephony/webhooks`.
- Result: CONFIRMED-WITH-LIMITS.
- Observed facts: call-event diagnostics export only to BigQuery, **after** the call finishes, with bounded retries and no durable replay; carrier callbacks terminate at Dograh. No sub-second hook toward our system is documented. Whether the webhook node fires when a run ends abnormally is unknown (docs: webhook nodes run "when reached" / after completion).
- Design impact: none for the decision; reconciler importance rises if the webhook does not fire on abnormal ends.
- Decision / fallback: stay with the run-ended notification (design default). Disconnect classification beyond `customer_hangup` stays `unknown` until observed.
- Doc patches: DP-05.
- Tests to add: TC-DG.17 "abnormal end with no webhook is resolved by the reconciler".
- **Live steps:** `python3 scripts/v07_midcall_procedure.py` prints the three calls (abrupt hang-up, airplane mode, agent-ended); capture webhook + get-run for each and note whether the webhook arrived at all.

### V08 — Start-call idempotency and double-dial safety
- Question: is the trigger idempotent; what happens on a retried POST and on timeout; response codes.
- Method: docs; live pending (real calls, counts against the cap).
- Evidence: `/api-reference/runs/trigger-workflow`, `/api-reference/errors`.
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: no idempotency key or header is documented; documented responses 200, 404, 422 (plus the global 400/401/403/500/501); `QUOTA_EXCEEDED` and `PHONE_NUMBER_NOT_CONFIGURED` exist as named telephony errors. The docs advise retrying 500s, which is unsafe for a call-placing endpoint.
- Design impact: none.
- Decision / fallback: rule validated by design and by the client test `test_timeout_is_reported_not_retried` (no automatic retry): after a timeout, 5xx or a crash the attempt is "unknown outcome → reconcile via V05 scan, never redial". 4xx means no run was created (to confirm live): mark the dispatch failed, alert, no automatic redial.
- Doc patches: DP-08.
- Tests to add: TC-DG.06 (exists), TC-DG.18 "5xx on trigger does not redial".
- **Live steps:** `v08_idempotency.py duplicate +NUMBER` (2 calls of budget), `v08_idempotency.py timeout +NUMBER` (0.2 s read timeout; if the API replies faster, add a delay proxy), then V05 scan to count runs per `attempt_id`; also record codes for malformed number, unknown workflow uuid, unpublished workflow, missing/invalid key.

### V09 — Reconnect via a new run seeded with `initial_context`
- Question: can a second run carry the saved summary; size limit; used by the prompt?
- Method: docs; live pending (2 calls).
- Evidence: `/core-concepts/context-and-variables`.
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: `initial_context` is an arbitrary JSON object; values are usable as `{{name}}` in agent prompts (with `{{name | fallback}}`); `gathered_context` is not available to prompts. No size limit documented. For telephony runs Dograh adds `caller_number` and `called_number`.
- Design impact: Memory-Specification payload should be flat string keys.
- Decision / fallback: proposed shape in `v09_reconnect_seed.py` (`is_reconnect`, `previous_attempt_id`, `previous_summary`, `previous_topics`, plus our ids); working limit 8 000 bytes until measured. Nested objects in prompts are unverified, so no nesting.
- Doc patches: DP-09.
- Tests to add: TC-MEM-new "seed context is flat and under the limit" (offline test exists in `tests/test_scripts.py`).
- **Live steps:** call 1 partial conversation, hang up; build summary; `v09_reconnect_seed.py +NUMBER PREV_ATTEMPT_ID "summary"`; read the transcript for acknowledgement. Find the size limit with the test-run endpoint (`POST /workflow/{id}/runs`, schema not read in this pass) or validation errors, not with real calls.

### V10 — Artifacts: recordings and transcripts
- Question: hosts, expiry, anonymous bearer, formats, lag, redirect behaviour, what `DOGRAH_ALLOWED_ARTIFACT_HOSTS` must contain.
- Method: docs; live pending; downloader implemented and tested offline.
- Evidence: `/api-reference/runs/download`, `/developer/environment-variables` (storage); `spike/dograh/artifact_download.py` + `tests/test_artifact_download.py` (6 tests).
- Result: CONFIRMED-WITH-LIMITS.
- Observed facts: the download endpoint takes the run's `public_access_token` (a UUID) in the **path** and answers **302 to a signed storage URL**; run objects expose both `*_url` and `*_public_url` fields; artifact types recording, transcript, user_recording, bot_recording; MinIO backend returns unsigned public-readable URLs, the S3 backend returns presigned URLs. Expiry, audio format, transcript format, lag and post-expiry behaviour are undocumented.
- Design impact: doc patch; the SSRF rule "no redirect to other hosts" becomes "one redirect, to an allowlisted host".
- Decision / fallback: `DOGRAH_ALLOWED_ARTIFACT_HOSTS` = Dograh API host + storage host (`MINIO_PUBLIC_ENDPOINT` host or `S3_ENDPOINT_URL`/S3 host); https only; ≤ 2 hops, each re-validated; size cap; timeout. Tokens in paths are redacted in evidence.
- Doc patches: DP-10.
- Tests to add: TC-DG.08 (exists); TC-DG.19 "redirect to a non-allowlisted host refused" (covered by `test_redirect_to_other_host_refused`).
- **Live steps:** `python3 scripts/v10_artifacts.py WORKFLOW_ID RUN_ID api.host,storage.host` right after a call, after 10 minutes and after 24 hours; record content types, sizes, redirect and expiry behaviour.

### V11 — Agents API: workflow sync
- Question: create from definition, update, publish, pin a published version, webhook node with credential and retry, versioning.
- Method: docs; live pending on a scratch workflow only.
- Evidence: `/api-reference/agents`, `/api-reference/agents/update`, `/developer/workflow-schema`; `docs/phase-0/evidence/V11/generated_definition.json` (generated by `v11_agents_sync.py`, validated against the documented schema rules by an offline test, **not yet accepted by a Dograh instance**).
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: create/update/validate endpoints exist; updating `workflow_definition` creates a new version; response carries `version_number`, `version_status`, `workflow_uuid`; **no publish endpoint and no credential endpoint are listed**; webhook node takes `credential_uuid` (no `retry_config` field); `max_call_duration` ≤ 1200 s; call dispositions configurable via `workflow_configurations`.
- Design impact: **design change possible** — "push then publish" (Dograh-Integration §4.3) may need a manual or UI publish step; the webhook credential must exist beforehand.
- Decision / fallback: sync service creates/updates the definition and then verifies `version_status`; if publishing cannot be done by API, an operator publishes in the UI and Django blocks campaign start until `version_status` shows published. Do not guess the status values.
- Doc patches: DP-11.
- Tests to add: TC-DG.20 "campaign cannot start on an unpublished agent version".
- **Live steps:** `python3 scripts/v11_agents_sync.py --apply` (creates `P0-SPIKE-*`), then read `evidence/V11/create_and_validate.json`; update the definition once and record how the new version becomes published; trigger it by Agent UUID with the V02 script.

### V12 — Concurrency, rate limits, backpressure
- Question: behaviour above `DEFAULT_ORG_CONCURRENCY_LIMIT`; API rate limits; effective concurrency.
- Method: docs plus a capacity derivation; live pending.
- Evidence: `/developer/environment-variables` ("Campaigns" section); `ai_calling agent/Business/Capacity-Planning.xlsx` (Assumptions sheet); `v12_concurrency.py`.
- Result: UNVERIFIED-NEEDS-LIVE.
- Observed facts: the limit is documented as concurrency for Dograh Campaigns (default 10); whether API-triggered runs are limited, and what the rejection looks like, is unknown. No API rate limits documented. Capacity-Planning assumptions (100 000 contacts/month, 35 % connect, 3.5 min average, 12 % disconnect, 70 % reconnect, 1.5 min extra, 8 h × 22 days, peak factor 1.8) give about 12 average and **about 22 peak concurrent connected calls** (excluding ring time), above the default of 10.
- Design impact: none, but treat the org limit as possibly unenforced.
- Decision / fallback: `DOGRAH_EFFECTIVE_CONCURRENCY = floor(min(carrier channels, server capacity, org limit if enforced) × 0.9)`; Django's semaphore enforces it regardless. Carrier channels and server capacity are inputs still missing (see PHASE-1-HANDOFF).
- Doc patches: DP-12.
- Tests to add: TC-DG.10 (exists).
- **Live steps:** on a scratch instance set `DEFAULT_ORG_CONCURRENCY_LIMIT=2`, trigger 3 short calls at once (budget 3), record the third response; poll get-run rapidly and look for rate-limit headers; ask the carrier for channels and calls-per-second.

### V13 — API key scope, rotation, network restriction
- Question: organization-scoped only; scopes; rotation; shown once; IP allowlisting; usage logging.
- Method: docs; live pending on a throwaway key.
- Evidence: `/api-reference/api-keys`.
- Result: CONFIRMED-WITH-LIMITS.
- Observed facts: keys are scoped to the organization, no operation scopes documented; endpoints under `/user/api-keys` (create, list, archive, reactivate); `last_used_at` exists; best practice is one key per environment and per service; archived key gives 401; "shown once" and IP allowlisting are not documented (the design places the allowlist at the reverse proxy).
- Design impact: none.
- Decision / fallback: rotation runbook: create new key → write to secrets manager → deploy → verify with a get-run → archive old key; keep the old key reactivatable for rollback. Mitigations unchanged (dedicated key, proxy allowlist, `last_used_at` monitoring).
- Doc patches: DP-13.
- Tests to add: TC-DG.21 "401 from Dograh pages operations (key archived)".
- **Live steps:** `python3 scripts/v13_key_rotation.py` prints the six checks (including whether key management needs a user JWT).

### V14 — Self-host production settings and security posture
- Question: confirm the required settings on the running instance.
- Method: docs; running instance not available.
- Evidence: `/developer/environment-variables`; `spike/dograh/scripts/v14_posture_check.py` (offline test).
- Result: CONFIRMED-WITH-LIMITS (settings exist as documented; none observed).

| Setting | Documented | Observed |
|---|---|---|
| `ENABLE_SIGNUP=false` | yes (403 on signup) | not observed |
| strong `OSS_JWT_SECRET` | yes (required, placeholder warning) | not observed |
| `TELEPHONY_WS_TOKEN_SECRET` + `ENFORCE=true` | yes, two-step rollout | not observed |
| private bucket with presigned URLs | yes via `ENABLE_AWS_S3=true` + `S3_*` (MinIO backend is public-readable) | not observed |
| HTTPS everywhere | `PUBLIC_BASE_URL` https | not observed |
| UI not internet-exposed | not a Dograh setting (network design) | not observed |
| Dograh DB separate from Django | yes (`DATABASE_URL` is Dograh's own) | not observed |
| `LOG_LEVEL` | default **DEBUG** | not observed |

- Design impact: doc patch (add `LOG_LEVEL`, `ENVIRONMENT=production`); note that customer numbers are stored in Dograh runs.
- Decision / fallback: self-hosted as instructed; cloud review questions (retention, regions, subprocessors, deletion) stay in OPEN-QUESTIONS in case cloud is reconsidered.
- Doc patches: DP-14, DP-15.
- Tests to add: TC-DG.12 (exists).
- **Live steps:** export the stack's environment into a file (do not paste it anywhere) and run `python3 scripts/v14_posture_check.py that.env`; check bucket policy and the proxy config by hand.
