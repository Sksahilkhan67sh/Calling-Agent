# PROGRESS

Status key: TODO / DOING / DONE / BLOCKED. Update after every phase (max 5 lines per phase).

## Phases
| # | Phase | Scope | Exit criteria | Status |
|---|---|---|---|---|
| 1 | Foundation | skeleton, settings split, Postgres, Celery+Redis, CI, `core`, `accounts` (JWT cookies, MFA, RBAC, throttle, axes), `audit` | login/refresh work, default-deny test passes, audit rows written | TODO |
| 2 | Data layer | `contacts` (encrypted phone + `phone_hmac`), `suppression`, `campaigns` (retry_policy, agent_config) | import + dedupe work, suppression matches by number, role-scoped CRUD | TODO |
| 3 | Dograh integration | `voice_runtime` (`VoiceRuntime`, `DograhClient`), workflow sync, `model_overrides` | sandbox call triggered, `provider_run_id` saved | TODO |
| 4 | Calling engine | `dialer`, `calls` state machine, `webhooks` (auth, receipt, verify-by-pull), reconciler | dial → run → webhook → state works; lost webhook recovered | TODO |
| 5 | Recovery + analysis | `recovery` (30s → 10min retry, reconnect as new run), `analysis`, lead scoring, `dashboard_api`, consent flow | mid-call drop retried, final output + score produced | TODO |
| 6 | Hardening | load tests, security tests, retention sweeper, runbooks | Test Plan exit criteria + release-gate regression pass | TODO |

## Phase log
<!-- one block per finished phase, max 5 lines: done / open [verify] / blockers -->
**Phase 1 DONE** — skeleton, settings split, Celery queues, core (default-deny RBAC, throttles, log redaction, /healthz), accounts (JWT cookies+CSRF, TOTP MFA, axes), audit (append-only trigger), CI. 23 tests pass; check --deploy, bandit, pip-audit clean.
Open: MFA enrolment flow not in docs → no-device login refused, `manage.py enroll_mfa` fallback; `CACHE_URL` env added (absent from Environment-Config); rate/axes limits are required env, no guessed defaults.
Deferred: `api_client` model/auth + drf-spectacular contract check until an endpoint needs them; INSERT-only DB role grant is a deploy step (trigger enforces now).
Blockers: none. Push refused (no GitHub write access for this session); commits are local.

## Open [verify] items (do not assume; use safe fallback)
- Dograh webhook body signing / signed timestamp
- Dograh run-listing API filter by `initial_context` (crash recovery after trigger call)
- Dograh failure status → `invalid_number` / `rejected` mapping per carrier
- Signature verification for Exotel, Telnyx, Cloudonix, Asterisk (confirmed: Twilio, Plivo, Vobiz, Vonage)
- STT / LLM / TTS vendors and carrier not chosen yet (config inside Dograh)

## Blockers
<!-- none -->
