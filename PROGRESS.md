# PROGRESS

Status key: TODO / DOING / DONE / BLOCKED. Update after every phase (max 5 lines per phase).

## Phases
| # | Phase | Scope | Exit criteria | Status |
|---|---|---|---|---|
| 1 | Foundation | skeleton, settings split, Postgres, Celery+Redis, CI, `core`, `accounts` (JWT cookies, MFA, RBAC, throttle, axes), `audit` | login/refresh work, default-deny test passes, audit rows written | TODO |
| 2 | Data layer | `contacts` (encrypted phone + `phone_hmac`), `suppression`, `campaigns` (retry_policy, agent_config) | import + dedupe work, suppression matches by number, role-scoped CRUD | DONE |
| 3 | Dograh integration | `voice_runtime` (`VoiceRuntime`, `DograhClient`), workflow sync, `model_overrides` | sandbox call triggered, `provider_run_id` saved | DONE |
| 4 | Calling engine | `dialer`, `calls` state machine, `webhooks` (auth, receipt, verify-by-pull), reconciler | dial → run → webhook → state works; lost webhook recovered | DONE |
| 5 | Recovery + analysis | `recovery` (30s → 10min retry, reconnect as new run), `analysis`, lead scoring, `dashboard_api`, consent flow | mid-call drop retried, final output + score produced | DONE |
| 6 | Hardening | load tests, security tests, retention sweeper, runbooks | Test Plan exit criteria + release-gate regression pass | DONE |

## Phase log
<!-- one block per finished phase, max 5 lines: done / open [verify] / blockers -->
**Phase 1 DONE** — skeleton, settings split, Celery queues, core (default-deny RBAC, throttles, log redaction, /healthz), accounts (JWT cookies+CSRF, TOTP MFA, axes), audit (append-only trigger), CI. 23 tests pass; check --deploy, bandit, pip-audit clean.
Open: MFA enrolment flow not in docs → no-device login refused, `manage.py enroll_mfa` fallback; `CACHE_URL` env added (absent from Environment-Config); rate/axes limits are required env, no guessed defaults.
Deferred: `api_client` model/auth + drf-spectacular contract check until an endpoint needs them; INSERT-only DB role grant is a deploy step (trigger enforces now).
Blockers: none. Push refused (no GitHub write access for this session); commits are local.

**Phase 2 DONE** — crypto helpers (Fernet rotation, phone HMAC), campaigns (+retry_policy, agent_config), contacts import (CSV/XLSX, dedupe, unique per campaign), suppression by hmac + contact id, role-scoped CRUD, audit on config/suppression writes. 58 tests pass; check --deploy, bandit, pip-audit clean.
Open: import format not in docs → header `phone_number`/`phone` required, numbers need a `+` country code (no default region); Sales read contacts across all campaigns (docs silent on scope); retry_policy/agent_config on create is Admin-only; `prompt_template_version` defaults to "v1".
Deferred: ContactDetail attempts/final_output (phases 4–5); dial-time `is_suppressed` use in phase 4, `agent_in_call` source in phase 5; retention sweeper must anonymise, not delete, suppressed contacts (FK is PROTECT).
Blockers: none.

**Phase 3 DONE** — `voice_runtime` (`VoiceRuntime`, `DograhClient`: trigger never retried, unknown outcome → `DialOutcomeUnknown`; get_run; SSRF-guarded artifact download; workflow push/publish), `model_overrides` from `agent_config.model_config_uuid` or env default, Admin-only `POST /v1/campaigns/{id}/sync-workflow` (locked, audited before/after, fixed consent + opt-out nodes). 84 tests pass; check --deploy, bandit, pip-audit clean.
Open: Dograh Agents API/run-lookup paths, workflow-definition schema, run payload keys, `model_overrides` body, `retry_config` shape not in docs → paths are required env (`DOGRAH_RUN_PATH`, `DOGRAH_WORKFLOW_PATH`), rest unconfirmed; sync endpoint not in API-Specification; consent line is the default text only (jurisdiction config → phase 5); only mocked HTTP tested, no sandbox run yet, `provider_run_id` column lands with `calls` in phase 4.
Blockers: none.

**Phase 4 DONE** — `calls` (CallAttempt, one transition service, never-connected retry/close decision), `dialer` (beat dispatcher with lease + skip_locked, dial task with DIAL_REQUESTED marker before trigger, dial-time suppression/campaign/window/capacity checks), `webhooks` (shared-secret auth w/ rotation, receipt-first, verify-by-pull, adopts run after crash), reconciler. 111 tests pass; check --deploy, bandit, pip-audit clean.
Open: unknown dial outcome past ceiling is left + logged, never redialed (no run lookup by initial_context [verify]); completion needs `DOGRAH_COMPLETED_DISPOSITIONS` (values unknown), anything else → retryable `unknown` drop; invalid_number/rejected not derivable from Dograh status → `provider_error`; calling window uses UTC; capacity = DB count under advisory lock, not a Redis semaphore.
Deferred (phase 5): State Saver + recording/transcript copy, mid-call retry decision/reconnect, analysis enqueue. Blockers: none.

**Phase 5 DONE** — State Saver (artifacts copied first, encrypted memory snapshot + disconnect_event + retry decision in one txn), reconnect as new run seeded with saved memory, in-call suppression (`agent_in_call`), recording kept only on explicit `granted` (private S3, SSE), rubric scoring + `analysis`/`final_output` (idempotent, swept), dashboard endpoints (audited transcript/recording access, Sales limited to final output/contact view). 128 tests pass; check --deploy, bandit, pip-audit clean.
Open: Dograh `gathered_context` key names (Memory Spec §2 names assumed), completed-disposition values, `turns` format; scoring constants (objection penalties, influencer weight, engagement rule) and `interest` fallback `undecided` are unconfirmed; summary/sentiment/suggestions only pass through from Dograh (no direct analysis LLM); transcript assumed UTF-8 text; recording stored only when consent == granted (`not_applicable` not stored).
Deferred: per-campaign score weights/bands + jurisdiction consent config, ContactHistory table, SSE (not in API spec), FinalOutput omits raw transcript/recording URL (use audited endpoints), retention sweeper (phase 6). Blockers: none.

**Phase 6 DONE** — retention sweeper (object deleted first, suppression untouched), full role×endpoint matrix, snapshot-failure-never-retries test, suppression bypass regressions (queued retry, re-import by number, in-call vs manual), in-process webhook flood + 429 tests, `loadtest/webhook_flood.py`, `RUNBOOK.md`. 142 tests pass; check --deploy, bandit, pip-audit clean.
Open: staging load tests not run (no environment) so `WEBHOOK_RATE_LIMIT_PER_MINUTE`/`DOGRAH_EFFECTIVE_CONCURRENCY` are unvalidated; snapshot-ordering test is failure-injection in one transaction, not randomized async timing; prompt-injection/output-guardrail suites are Dograh-side, untested here; `RETENTION_DAYS` is a required compliance decision; contact-level erasure/anonymisation of suppressed contacts and FinalOutput retention not implemented.
Blockers: none. Pushing not attempted (earlier push was refused); all commits local.

## Open [verify] items (do not assume; use safe fallback)
- Dograh webhook body signing / signed timestamp
- Dograh run-listing API filter by `initial_context` (crash recovery after trigger call)
- Dograh failure status → `invalid_number` / `rejected` mapping per carrier
- Signature verification for Exotel, Telnyx, Cloudonix, Asterisk (confirmed: Twilio, Plivo, Vobiz, Vonage)
- Dograh Agents API (create/update/publish), run-lookup response keys, workflow-definition schema
- STT / LLM / TTS vendors and carrier not chosen yet (config inside Dograh)

## Blockers
<!-- none -->
