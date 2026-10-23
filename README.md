# AI Calling Agent — Django Backend

Backend for an outbound AI calling platform. Django owns contacts, campaigns, scheduling, compliance (suppression, recording consent), call state, recovery, analysis and the dashboard API. **Dograh** owns the live call (telephony, STT, LLM, TTS). Django never touches live audio.

Specs live in [`docs/`](docs/ai_calling%20agent) (V3). Build status and open `[verify]` items are in [`PROGRESS.md`](PROGRESS.md); operations are in [`RUNBOOK.md`](RUNBOOK.md).

## Stack

Django 5.2 + DRF, PostgreSQL 16, Celery + Redis, S3-compatible private bucket, Python 3.13. Auth: JWT in HttpOnly cookies with CSRF, TOTP MFA for privileged roles, django-axes lockout.

## How a call flows

```
dispatcher (beat, 10s) ──► dial task ──► Dograh trigger ──► run (Dograh dials, converses)
   claims due attempts        │ suppression, campaign, window,        │
   (SKIP LOCKED + lease)      │ capacity re-checked at dial time      ▼
                              │ DIAL_REQUESTED marker committed   run ends → webhook node
                              ▼ before the trigger call                  │
                       provider_run_id saved                             ▼
                                                      POST /webhooks/dograh/run-completed
                                                      auth → receipt written → 200
                                                                         │
                                          Celery task pulls the run from Dograh (verify-by-pull)
                                          copies transcript/recording → applies state transition
                                                                         │
                       ┌─────────────────────────┬───────────────────────┴──────────┐
                       ▼                         ▼                                  ▼
               never connected            ended normally                     dropped mid-call
            retry policy → retry or      → Completed                  save snapshot → retry decision
                  Closed                  → analysis + final output     reconnect (new run, seeded memory)
                                                                        or CompletedPartial → analysis
```

Safety properties that the code and tests enforce:

- The webhook body is only a notification. The pulled run decides; a run that belongs to another attempt is rejected.
- The trigger call is never auto-retried. A timeout or 5xx is an "unknown outcome" that is reconciled, never redialed.
- Receipts are unique on `(provider, run_id, event_type)` and written before the `200`. Duplicates apply once; terminal attempts cannot change.
- Suppression is checked at dial time by contact id and `phone_hmac`, so a queued retry or a re-imported number is still blocked.
- Artifacts are copied to private storage before any state change; a failed copy blocks the transition until it succeeds.
- Recordings are stored only on explicit `granted` consent. Absent or unclear is treated as denied.
- Phone numbers, transcripts and working memory are encrypted at rest. Logs redact secrets, phone numbers and recording URLs.

## Layout

```
backend/
  config/            settings (base/dev/prod/test), urls, celery
  apps/
    core/            crypto (Fernet rotation, phone HMAC), RBAC permissions, throttles, log redaction, /healthz
    accounts/        users, roles, JWT cookies, MFA, lockout
    audit/           append-only audit events
    campaigns/       campaign, retry_policy, agent_config, Dograh workflow sync
    contacts/        CSV/XLSX import, dedupe, encrypted phone + blind index
    suppression/     single DNC/opt-out table and check service
    voice_runtime/   VoiceRuntime protocol + DograhClient (the only module that talks to Dograh)
    calls/           call attempts, state machine, disconnect events, transcripts, recording refs, reconciler
    dialer/          dispatcher and dial task
    webhooks/        Dograh webhook auth, receipts, verify-by-pull task
    recovery/        State Saver, retry decision, reconnect seed, artifact copy, retention sweeper
    analysis/        lead scoring, analysis, final output
    dashboard_api/   read endpoints, audited transcript/recording access, analytics
  tests/
  loadtest/          staging webhook-flood script
```

## Roles

| Role | Access |
|---|---|
| Admin | Everything, including writing retry policy / agent config, workflow sync, manual suppression |
| Campaign Manager | Own campaigns, contacts, attempts, transcripts, recordings, analytics (read); cannot write policy or agent config |
| Sales/Follow-up | Read-only contact views and final outputs; no raw transcripts or recordings |

Views declare `roles` per HTTP method; anything undeclared is denied, and a test enforces that every project view declares them.

## API

All under `/v1` except the webhook. Authentication: `POST /v1/auth/token`, `/v1/auth/token/refresh`, `/v1/auth/logout`.

| Endpoint | Purpose |
|---|---|
| `GET/POST /v1/campaigns`, `GET/PATCH /v1/campaigns/{id}` | Create (with contact file), list, status |
| `GET/PUT /v1/campaigns/{id}/retry-policy`, `/agent-config` | Config (writes Admin-only, audited before/after) |
| `POST /v1/campaigns/{id}/sync-workflow` | Render `agent_config` and push + publish to Dograh (Admin) |
| `GET /v1/campaigns/{id}/contacts`, `GET /v1/contacts/{id}` | Contacts; detail includes attempts and final output |
| `POST /v1/contacts/{id}/suppress` | Manual do-not-call |
| `GET /v1/contacts/{id}/final-output` | Score, interest, summary (references only, no raw artifacts) |
| `GET /v1/call-attempts/{id}` and `/transcript`, `/recording`, `/disconnect-events` | Attempt detail; transcript and recording access is audited, recording is a short-lived presigned URL |
| `GET /v1/dashboard/campaigns/{id}/analytics` | Status counts, score and temperature distribution, disconnect and reconnect rates |
| `POST /webhooks/dograh/run-completed` | Dograh notification (shared-secret header) |

`sync-workflow` and the contact-detail extension are not in `API-Specification.yaml`; live-update streaming (SSE) is not implemented.

## Getting started

Prerequisites: Python 3.13, PostgreSQL 16, Redis.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Postgres matching the test settings
createuser calling -P            # password: calling
createdb -O calling calling

pytest -q                         # test settings supply every required env var
```

Run locally with `DJANGO_SETTINGS_MODULE=config.settings.dev` and the variables below exported:

```bash
python manage.py migrate
gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker
celery -A config worker -Q dial,webhook,recovery,analysis,default
celery -A config beat           # exactly one instance
```

Admin and Campaign Manager logins require MFA. There is no enrolment flow in the docs, so enrol a device with `python manage.py enroll_mfa`.

## Configuration

Configuration is environment variables only. Required ones have no defaults, and startup fails with a `KeyError` naming the missing variable.

| Group | Variables |
|---|---|
| Django | `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXY_COUNT` (optional), `LOG_LEVEL` (optional), `CACHE_URL` (prod) |
| Database / broker | `PRIMARY_DB_URL`, `PRIMARY_DB_POOL_SIZE`, `CALL_QUEUE_BROKER_URL` |
| Auth | `JWT_SIGNING_KEY`, `JWT_ACCESS_LIFETIME_SECONDS` (opt), `AXES_FAILURE_LIMIT`, `AXES_COOLOFF_MINUTES` (opt), `MFA_REQUIRED_ROLES` (opt), `API_RATE_LIMIT_PER_MINUTE` |
| Encryption | `FIELD_ENCRYPTION_KEYS` (comma list, newest first), `PHONE_HMAC_KEY` |
| Dograh | `DOGRAH_BASE_URL`, `DOGRAH_API_KEY`, `DOGRAH_REQUEST_TIMEOUT_SECONDS`, `DOGRAH_RUN_PATH`, `DOGRAH_WORKFLOW_PATH`, `DOGRAH_DEFAULT_MODEL_CONFIG_UUID` (opt), `DOGRAH_ALLOWED_ARTIFACT_HOSTS`, `DOGRAH_MAX_ARTIFACT_BYTES`, `DOGRAH_ARTIFACT_DEADLINE_SECONDS`, `DOGRAH_COMPLETED_DISPOSITIONS`, `DOGRAH_EFFECTIVE_CONCURRENCY`, `PUBLIC_BASE_URL` |
| Webhook | `DOGRAH_WEBHOOK_SECRET`, `DOGRAH_WEBHOOK_SECRET_PREVIOUS` (rotation only), `DOGRAH_WEBHOOK_HEADER_NAME` (opt), `WEBHOOK_RATE_LIMIT_PER_MINUTE` |
| Reconciler / storage | `RECONCILE_CEILING_SECONDS`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_ENDPOINT_URL` (opt), `RECORDING_URL_TTL_SECONDS`, standard AWS credential variables |
| Retention | `RETENTION_DAYS` (a compliance decision, set deliberately) |

The webhook, concurrency and retention limits should come from load testing and compliance review, not guesses.

## Background jobs

| Task | Queue | Schedule |
|---|---|---|
| `dialer.dispatch_due` | dial | every 10s |
| `dialer.dial_attempt` | dial | on demand |
| `webhooks.process_run_result` | webhook | on demand (retries on Dograh errors) |
| `calls.reconcile_stuck` | recovery | every 60s |
| `recovery.sweep_retention` | recovery | daily |
| `analysis.analyze_attempt` | analysis | on completion |
| `analysis.sweep_unanalyzed` | analysis | every 5 min |

Tasks use `acks_late`, `reject_on_worker_lost`, time limits and are idempotent.

## Testing and quality gates

```bash
cd backend
pytest -q                                              # 142 tests, real PostgreSQL, mocked Dograh and S3
python manage.py check --deploy                        # with config.settings.prod and its env
bandit -q -ll -r apps config
pip-audit -r requirements.txt
python manage.py makemigrations --check --dry-run
```

CI (`.github/workflows/ci.yml`) runs all of these. Failure paths are tested alongside the happy paths: duplicate and forged webhooks, crash mid-dial, lost webhook, suppression added mid-wait, failed artifact copy, snapshot write failure, expired retention, and the role-by-endpoint matrix.

Run the tests in a clean environment: exported production-style variables override the test defaults.

## Known gaps

Several Dograh details are not in the docs, so they are assumptions and are not verified against a real Dograh instance: the Agents API paths and workflow-definition schema, the key names in a finished run's data, the values that mean a normal completion, and the `model_overrides` shape. The full list of open `[verify]` items, scoring constants and deferred work (per-campaign score weights, jurisdiction consent settings, contact erasure) is in [`PROGRESS.md`](PROGRESS.md).
