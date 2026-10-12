# Environment variables (Phase 1)

Source of truth: Environment-Config §2. A test (`tests/config/test_settings.py::test_env_variables_doc_matches_settings`)
fails if a variable read by the settings is missing here, or listed here but never read.
Values are never printed in errors; a missing/invalid variable stops start-up and the message names only the variable.

Business configuration (retry policy, agent config) is **not** an environment variable (Environment-Config §1).

## Settings variables

| Variable | Required | Secret | Default (dev/test only) | Consumer |
|---|---|---|---|---|
| `DJANGO_SECRET_KEY` | all envs | yes | none | Django signing. Prod/staging: ≥ 50 chars, no placeholder, ≠ `JWT_SIGNING_KEY` |
| `DJANGO_ALLOWED_HOSTS` | all envs | no | none | `ALLOWED_HOSTS`; comma list, no wildcard/scheme/port |
| `PRIMARY_DB_URL` | all envs | yes | none | `postgres://user:pass@host:port/db?sslmode=…`; prod/staging require `sslmode` require/verify-ca/verify-full |
| `PRIMARY_DB_POOL_SIZE` | all envs | no | none | psycopg pool `max_size` (Environment-Config: 5 dev / 20 staging / 50 prod) |
| `CACHE_REDIS_URL` | all envs | yes | none | Redis for cache, rate-limit counters, locks; readiness PING. Use a different Redis DB index than the broker. **New name, see DOC-PATCHES DP1-01** |
| `CALL_QUEUE_BROKER_URL` | all envs | yes | none | Celery broker (Redis by default, RabbitMQ allowed) |
| `JWT_SIGNING_KEY` | all envs | yes | none | SimpleJWT signing key (HS256, fixed in code). ≠ `DJANGO_SECRET_KEY`; prod/staging ≥ 50 chars (**raised from 32 in Phase 2**) |
| `FIELD_ENCRYPTION_KEYS` | all envs | yes | none | `id:base64(32 bytes)[,id:base64…]`, newest first. Used by `core.crypto.FieldCipher` |
| `PHONE_HMAC_KEY` | all envs | yes | none | base64, ≥ 32 bytes. Blind index key (`core.crypto.blind_index`) |
| `DOGRAH_EFFECTIVE_CONCURRENCY` | all envs | no | none | Positive integer. Read and validated now, **unused until Phase 4**. Must come from carrier channels + load test, not Dograh's default 10 (Phase 0 DP-12) |
| `DOGRAH_WEBHOOK_HEADER_NAME` | no | no | `X-Dograh-Webhook-Secret` | Header name treated as sensitive by log redaction |
| `API_RATE_LIMIT_PER_MINUTE` | prod/staging | no | `1000` | Throttle scopes `api-user`, `api-client`. **Must come from load-test results (Threat Model risk #6); record source run/date when set** |
| `WEBHOOK_RATE_LIMIT_PER_MINUTE` | prod/staging | no | `1000` | Throttle scope `webhook`. Same rule (Load Test Plan §4.3) |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | prod/staging | no | `5` | Throttle scope `login`, per client address. Security default, not load-derived. **Explicit in prod since Phase 2** |
| `CORS_ALLOWED_ORIGINS` | prod/staging | no | empty (dev uses `http://localhost:3000`) | Comma list of origins (`scheme://host[:port]`); no wildcard/path. Credentialed CORS is on (cookie auth), so prod requires a non-empty `https://` list. **Required in prod since Phase 2** |
| `JWT_ACCESS_LIFETIME_SECONDS` | no | no | `900` | Access-token lifetime, 60–3600 (Phase 2) |
| `JWT_REFRESH_LIFETIME_SECONDS` | no | no | `86400` | Refresh-token lifetime, 3600–2592000. Tokens rotate on every use, so this is an idle timeout (Phase 2) |
| `AUTH_COOKIE_SAMESITE` | no | no | `Lax` | `Lax` or `Strict` for the auth and CSRF cookies; `None` is refused (Phase 2) |
| `AUTH_COOKIE_DOMAIN` | no | no | empty | Optional cookie domain. Empty enables `__Host-` cookie names; set switches to `__Secure-` (Phase 2) |
| `AUTH_TOKENS_IN_BODY` | no | no | `false` | Return tokens in the login body for non-browser clients. Keep `false` for the dashboard (Phase 2) |
| `CSRF_TRUSTED_ORIGINS` | prod/staging | no | empty (dev uses `http://localhost:3000`) | Origins allowed to send unsafe requests under cookie auth; prod requires a non-empty `https://` list (Phase 2) |
| `AXES_FAILURE_LIMIT` | prod/staging | no | `5` | Failed password/MFA attempts before lockout. No prod default (Phase 2; wired in P2-10) |
| `AXES_COOLOFF_MINUTES` | no | no | `15` | Lockout duration (Phase 2; wired in P2-10) |
| `TRUSTED_PROXY_COUNT` | prod/staging | no | `0` | Reverse proxies in front of the API, 0–10. Client IP = the `X-Forwarded-For` entry that many hops from the right; no prod default (Phase 2) |
| `MFA_REQUIRED_ROLES` | no | no | `Admin,Campaign Manager` | Roles that must use TOTP. Names must be known roles; prod requires Admin and Campaign Manager (Phase 2) |
| `MFA_ISSUER_NAME` | no | no | `AI Calling Agent` | Issuer label shown in authenticator apps (Phase 2) |
| `MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS` | no | no | `600` | Lifetime of the single-purpose MFA enrolment credential, 60–1800 (Phase 2) |
| `API_CLIENT_LAST_USED_WRITE_INTERVAL_SECONDS` | no | no | `60` | Minimum seconds between `api_client.last_used_at` writes, 1–3600 (Phase 2) |
| `LOG_LEVEL` | no | no | `INFO` (dev forces `DEBUG`) | Root log level |
| `APP_VERSION` | no | no | empty | Optional git SHA shown on health endpoints; `[A-Za-z0-9._-]{1,40}` |

## Process variables (not read by Django settings)

| Variable | Used by | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | manage.py, ASGI/WSGI, Celery | `config.settings.prod` in production, `dev` in `manage.py` default |
| `WEB_CONCURRENCY` | `docker/gunicorn.conf.py` | Gunicorn worker count (default 2) |
| `GUNICORN_BIND` | `docker/gunicorn.conf.py` | Default `0.0.0.0:8000` inside the container |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `docker/compose.dev.yml` | Dev database container; values come from `.env` |
