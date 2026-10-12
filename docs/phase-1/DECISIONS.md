# Phase 1 decisions

Short ADR-style notes. "Ref" points to the design document the decision follows.

## D-01 Pinned versions (confirmed from PyPI on 2026-10-11; no pre-releases; none younger than 14 days)

Hashed lock files were resolved with pip's `--uploaded-prior-to` (cut-off 2026-09-27) and compiled with
`pip-compile --generate-hashes` against those constraints. A script re-checked all 102 pins: none younger than 14 days.

| Package | Pin | Released | Note |
|---|---|---|---|
| Django | 5.2.17 | 2026-08-04 | 5.2 is the latest 5.x LTS line. 6.x exists; not used (design says 5.x LTS). 5.2.18 was too new |
| djangorestframework | 3.18.1 | 2026-09-07 | |
| drf-spectacular | 0.30.0 | 2026-07-06 | |
| psycopg / psycopg-binary | 3.3.6 | 2026-09-18 | `[binary,pool]`: wheels only, no compiler in the image |
| psycopg-pool | 3.3.3 | 2026-09-22 | |
| celery (`[redis]`) | 5.6.3 | 2026-03-26 | kombu 5.6.2 resolves redis-py 6.4.0 (2025-08-07) |
| argon2-cffi | 25.1.0 | 2025-06-03 | |
| cryptography | 50.0.1 | 2026-08-25 | 50.0.2 was too new |
| django-cors-headers | 4.9.0 | 2025-09-18 | |
| gunicorn / uvicorn / uvicorn-worker | 26.2.0 / 0.54.0 / 0.4.0 | 2026-08-24 / 2026-09-25 / 2025-09-20 | `uvicorn-worker` is the maintained Uvicorn worker class |
| pytest / pytest-django / pytest-cov | 9.1.1 / 4.14.0 / 7.1.0 | 2026-06-19 / 2026-08-10 / 2026-03-21 | |
| freezegun | 1.5.5 | 2025-08-09 | used by the `frozen_time` fixture |
| ruff / mypy | 0.16.9 / 2.3.1 | 2026-09-24 / 2026-08-15 | |
| django-stubs / djangorestframework-stubs | 6.1.1 / 3.18.1 | 2026-09-14 / 2026-08-25 | |
| bandit / pip-audit / pre-commit / pip-tools | 1.9.4 / 2.10.1 / 4.6.2 / 7.6.1 | 2026-02-25 / 2026-06-10 / 2026-08-10 / 2026-08-12 | |

Not added (YAGNI, per the phase rules): django-environ (our readers are small and fail-fast with secret-safe errors),
whitenoise (no static files; the admin is not mounted), structlog (stdlib logging plus ~60 lines of formatter is enough),
factory-boy (one model, no factories needed), pytest-xdist, simplejwt, axes, boto3, django-storages, channels, sentry.
`pip-audit` result: no known vulnerabilities (prod and dev locks). No accepted exceptions, so no expiry entries.

## D-02 Updating pins
`make lock` recompiles. Dependabot opens weekly grouped PRs. Reviewers check that new pins are at least 14 days old
unless the release is the only patched version for a known vulnerability.

## D-03 Settings split
`base` (shared), `dev`, `test`, `prod`, `staging`. `staging` is `from .prod import *`: staging has the production
posture and only environment values differ (Environment-Config §3). `DEBUG` is a literal `False` in `base` and `prod`,
and no variable can turn it on in staging/prod. Dev has no secret defaults: values come from `.env`. Only `test.py` sets
fake values (tests only, via `setdefault`).
Prod fails to start on: any missing required variable, secret key < 50 chars or a placeholder, `JWT_SIGNING_KEY` equal to
`DJANGO_SECRET_KEY` or < 32 chars, unset API/webhook rate limits, invalid key material, and a DB URL without a verifying
`sslmode`. The last check goes beyond the design text (safer option; Security Architecture assumes encryption in transit).

## D-04 Database
`PRIMARY_DB_URL` is parsed by a small tested function (no extra dependency). psycopg pool: `max_size = PRIMARY_DB_POOL_SIZE`,
`min_size = min(2, size)`; `CONN_MAX_AGE = 0` because the pool handles reuse. `ATOMIC_REQUESTS = False`: the dialer
(Phase 4) needs explicit transactions around `SELECT … FOR UPDATE SKIP LOCKED`. All models use UUID primary keys and
`timestamptz` (`USE_TZ=True`). `DEFAULT_AUTO_FIELD` is only set to silence the warning for auto-created M2M tables.

## D-05 Celery
JSON only, `acks_late`, `reject_on_worker_lost`, prefetch 1, soft/hard limits 270/300 s, no result backend
(`task_ignore_result`; nothing needs results yet), `broker_connection_retry_on_startup`, Redis visibility timeout 1 h.
Queues declared but unused: `default`, `dial`, `webhooks`, `recovery`, `analysis`. **The design (Backend Design §6) says
`webhook`, the phase prompt says `webhooks`; Phase 1 follows the prompt. See DP1-02.** Beat schedule contains only the
heartbeat. Worker root-logger hijacking is disabled so our JSON logging and redaction stay in force.
Rule: the durable retry schedule lives in PostgreSQL (`call_attempt.next_dispatch_at`); broker delays are an
optimisation only (Backend Design §6, Environment-Config §2.5). Task convention: accept `log_context` and run the body inside
`context(**log_context)`.

## D-06 Field encryption (`core.crypto`)
AES-256-GCM, 96-bit random nonce. Format `v1:<key_id>:<nonce>:<ciphertext+tag>` (base64url). Key set
`FIELD_ENCRYPTION_KEYS="id:base64,id:base64"`, newest first; encrypt uses the first key; decrypt picks the key by the id
in the header. AAD = `v1|key_id|context` where context is mandatory (e.g. `contact.phone_encrypted`), so a ciphertext
moved to another column or relabelled with another key id fails. Base64 decoding is strict (an earlier draft silently
skipped invalid characters; fixed with a test). Errors never contain plaintext or key material.
Rejected: Fernet/MultiFernet (no AAD, no key-id header, AES-128).

## D-07 Blind index
`HMAC-SHA256(key, purpose || 0x00 || value)`, hex. `purpose` gives domain separation (`phone`, `suppression`, …).
Input must already be canonical; E.164 normalisation is Phase 3 (`contacts`). Rotation of `PHONE_HMAC_KEY` is a planned
re-computation of every stored index (read plaintext through the cipher, recompute, swap in one migration with a dual-index
window); it is intentionally not implemented now.

## D-08 Logging and redaction
Stdlib logging; one JSON object per line; correlation fields from `contextvars`. The redaction filter is attached to every
handler, and also covers Gunicorn/Uvicorn loggers. Rules: secret-named fields, `Bearer`/JWT/vendor token shapes,
`key=value` secrets, URL userinfo passwords, URL query tokens (`token`, `signature`, `sig`, `key`, `expires`, `X-Amz-*`),
**recording/transcript/artifact URLs (host kept, path dropped)**, private key blocks, and phone numbers (E.164 →
`+<cc>***<last2>`, other 10–15 digit numbers → `***<last2>`). Over-redaction is accepted: a 10–15 digit number such as an
epoch timestamp is masked too. Regexes use bounded quantifiers; tests cap hostile inputs at 2 s. The Gunicorn access log
format uses the path only (`%(U)s`), never the query string.

## D-09 Permissions, authentication, admin
`DEFAULT_PERMISSION_CLASSES = [DefaultDeny]` and `DEFAULT_AUTHENTICATION_CLASSES = []` by design: authentication is Phase 2,
so every view must opt in. `tests/test_default_deny.py` walks the URL conf and fails on non-DRF views, empty permission
lists, silent default deny, and anonymous views outside a reviewed allowlist (negative cases included). The Django admin
is **not mounted** and not installed. Sessions and `AuthenticationMiddleware` are not installed until Phase 2.

## D-10 Throttles
Scopes `login`, `api-user`, `api-client`, `webhook` on `SimpleRateThrottle` subclasses; rates come from settings. The default
throttle is `api-user`; health views opt out. `LOGIN_RATE_LIMIT_PER_MINUTE` defaults to 5 per client address: a security
default, not load-derived (see OQ-04). The cache is resolved per throttle instance so tests can swap backends.

## D-11 Health
`/healthz` is liveness only. `/readyz` checks PostgreSQL (`SELECT 1`), Redis (`PING`) and the broker concurrently with a 2 s
cap; failures return 503 with the check names and booleans only. In staging/prod `SECURE_REDIRECT_EXEMPT` excludes both
paths so in-cluster HTTP probes are not redirected to HTTPS; Docker's own healthcheck sends the first allowed host.

## D-12 User model
`User(AbstractUser)` with UUID pk, `username` removed, `USERNAME_FIELD = "email"`, lowercase normalisation on save plus a
database `UNIQUE (lower(email))` constraint (bulk paths cannot bypass it). Nothing else; Phase 2 adds roles/MFA.

## D-13 API contract check
`scripts/check_api_contract.py` (informational in Phase 1): exit 1 only on drift for implemented paths (undocumented
implemented path, missing method, parameter mismatch, missing response code). Path-parameter names are not compared (the
normalised path template is). Unimplemented spec paths (21 operations now) are listed and ignored. Health routes are internal
and excluded from the schema. **Later phases flip "not yet implemented" into a failure as each app lands.**

## D-14 Containers and CI
Multi-stage image, hash-enforced install with `--only-binary`, non-root uid 10001, no migrations in the entrypoint. Base image
is `python:3.12-slim-bookworm` (minor line, not `latest`; digest pinning is left to the registry policy/Dependabot). Compose
publishes only on 127.0.0.1 and takes credentials from `.env`. GitHub Actions are pinned by commit SHA (checkout v7.0.1,
setup-python v7.0.0, upload-artifact v7.0.2, gitleaks-action v3.0.0); service images are pinned to a major line only.
Migration rule: every migration must be additive and backward-compatible (Deployment-Guide §5).

## D-15 Type checking
mypy `strict` for `apps.core.*` and `config.*`; the User model and tests are checked more loosely (`ignore_errors` for tests
and migrations). Two `type: ignore` comments exist on the custom manager override, required by django-stubs.
