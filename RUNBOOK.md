# Backend operations runbook

Complements `docs/.../Deployment/Incident-Runbook.md` and `Rollback-Runbook.md` with what the Django code actually does.

## Processes
- API: `gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker`
- Workers (one pool per queue so analysis cannot starve dialing): `celery -A config worker -Q dial`, `-Q webhook`, `-Q recovery`, `-Q analysis`, `-Q default`
- Beat (exactly one instance): `celery -A config beat` — dispatch 10s, reconcile 60s, unanalyzed sweep 5min, retention daily
- Every setting is an env var and none has a guessed default; startup fails with `KeyError` naming the missing one. Secrets: `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`, `FIELD_ENCRYPTION_KEYS`, `PHONE_HMAC_KEY`, `DOGRAH_API_KEY`, `DOGRAH_WEBHOOK_SECRET(_PREVIOUS)`.

## Dial outcome unknown (trigger timed out / 5xx)
Symptom: log `dial outcome unknown past ceiling`; attempt `Initiated`, `started_at` set, `provider_run_id` empty. Django never redials these (the trigger is not idempotent and runs cannot be listed by `initial_context` [verify]).
1. A late webhook adopts the run by itself (attempt id round-trips in `initial_context`).
2. Otherwise find the run in the Dograh UI by `initial_context.attempt_id`. Found: set `provider_run_id` in a Django shell (the reconciler then applies it). Not found: mark the attempt failed via `apps.calls.services.fail_attempt(attempt, "provider_error")` inside `transaction.atomic()` with attempt and contact locked.
3. Unresolved attempts count against `DOGRAH_EFFECTIVE_CONCURRENCY`; resolve them or capacity shrinks.

## Webhook problems
- 401 spike: wrong or rotated secret. Rotate by setting `DOGRAH_WEBHOOK_SECRET_PREVIOUS` to the old value, deploying, switching Dograh's credential, then clearing the previous value.
- Receipts stuck in `received`: task retries exhausted (Dograh unreachable). The reconciler pulls the run once the attempt is older than `RECONCILE_CEILING_SECONDS`; no manual step needed unless it keeps logging `reconcile pull failed`.
- Receipts `rejected`: pulled run did not match the claimed attempt — treat as a security event.

## Suppression
Checked at dial time by contact id and `phone_hmac`. If a suppressed number was dialed, stop the dialer (`status=paused` on active campaigns), export `calls_callattempt` for the number's `phone_hmac`, and treat as release-blocking.

## Recordings, transcripts, retention
- Recordings are stored only on explicit `granted` consent, under `recordings/<attempt_id>` in the private bucket with SSE; humans get presigned URLs (`RECORDING_URL_TTL_SECONDS`) and every access writes an audit row.
- `sweep_retention` deletes expired recordings (object first), transcripts and working memory after `RETENTION_DAYS`; it never touches `suppression`. If the object delete fails the row is kept and retried next day.

## Migrations and rollback
Migrations are additive. Roll code back first; do not reverse a migration while workers run. A destructive change needs two releases (stop using, then drop).

## Backlog
Queue depth: `redis-cli -n <broker db> llen dial` (and `webhook`, `recovery`, `analysis`). Growth on `dial` with idle capacity means the window/campaign status gates are holding attempts; growth on `webhook` means Dograh pulls are slow.

## Load test
`backend/loadtest/webhook_flood.py` (staging only) replays an outage-shaped webhook burst. Limits (`WEBHOOK_RATE_LIMIT_PER_MINUTE`, `DOGRAH_EFFECTIVE_CONCURRENCY`) must be set from its results.
