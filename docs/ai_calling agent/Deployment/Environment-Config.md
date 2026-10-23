# AI Calling Agent — Environment Configuration

Complete outbound calling workflow, with disconnect recovery · v1.1 · Status: Draft for review (Dograh + Django update)

**Related documents:** Infrastructure Architecture v1.0 · Security Architecture v1.0 · Deployment Guide v1.0 · Database Design v1.0 · Webhook Specification v1.0 · API Specification v1.0

**Purpose:** a concrete reference for every configuration value the system needs to run, per environment — where it lives, whether it's a secret, and what changes between Development, Staging, and Production. Deployment Guide §2 references this document's checklist items.

---

## 1. Two kinds of configuration — read this first

This system has two entirely different configuration layers, and conflating them is a common source of deployment mistakes:

| Layer | Examples | Where it lives | Changed by |
|---|---|---|---|
| **Infrastructure config** (this document) | Database connection strings, provider API keys, service URLs, log levels | Environment variables / secrets manager, set at deploy time | A deployment (Deployment Guide §6) |
| **Business config** (NOT this document) | Retry policy (max retries, spacing, calling window), agent persona/script | Primary DB (`retry_policy`, `agent_config` tables), set via Admin Dashboard | An Admin, at runtime, no deployment (System Architecture, Database Design §2.2–2.3) |

**Rule of thumb:** if a campaign manager or admin should be able to change it without waiting for engineering, it belongs in Business config and does **not** appear as an environment variable. Retry policy defaults shown as examples in earlier documents (max retries = 2, calling window 10 AM–6 PM) are **database row defaults for a new campaign**, not environment variables — do not create an env var for these.

---

## 2. Environment variable reference

### 2.1 Database & data layer

| Variable | Description | Secret? | Dev | Staging | Production |
|---|---|---|---|---|---|
| `PRIMARY_DB_URL` | Connection string for the Primary DB (Database Design) | Yes | Local/dev DB | Staging DB | Production DB, read/write replica-aware |
| `PRIMARY_DB_POOL_SIZE` | Connection pool size per service instance | No | `5` | `20` | `50` (tune per Infrastructure Architecture §6) |
| `OBJECT_STORAGE_BUCKET` | Bucket/container for recordings (Database Design §2.9) | No | `dev-recordings` | `staging-recordings` | `prod-recordings` |
| `OBJECT_STORAGE_CREDENTIALS` | Access credentials for object storage | Yes | Sandbox | Sandbox | Production, encrypted at rest per Security Architecture §4 |
| `MEMORY_STORE_URL` | Connection string for the working-memory in-memory store (Memory Specification, Infrastructure Architecture §4) | Yes | Local | Staging cluster | Production cluster |
| `ANALYTICS_STORE_URL` | Connection string for the denormalized Final Output / dashboard read-model | Yes | Local | Staging | Production |

### 2.2 Voice runtime — Dograh (replaces the former telephony provider variables)

Telephony, STT, LLM and TTS for the live call are configured **inside Dograh** (Dograh Integration §4.4). Django only holds what it needs to drive Dograh and receive its webhook.

| Variable | Description | Secret? | Notes |
|---|---|---|---|
| `DOGRAH_BASE_URL` | Base URL of the Dograh API (self-hosted internal URL, or hosted URL) | No | Private network URL in Production for self-hosted |
| `DOGRAH_API_KEY` | Organization-scoped API key sent as `X-API-Key` | Yes | Dedicated key for the backend only; shown once by Dograh, so store it immediately; rotate by creating a new key and archiving the old one |
| `DOGRAH_DEFAULT_MODEL_CONFIG_UUID` | Named model configuration used when a campaign has no override | No | UUID reference only; provider keys are never copied into Django |
| `DOGRAH_WEBHOOK_SECRET` | Value Dograh sends in the webhook header; verified in constant time (Webhook Specification §4A.2) | Yes | At least 32 random bytes; unique per environment |
| `DOGRAH_WEBHOOK_SECRET_PREVIOUS` | Previous secret accepted only during a rotation window | Yes | Empty outside rotation |
| `DOGRAH_WEBHOOK_HEADER_NAME` | Header carrying the secret | No | e.g. `X-Dograh-Webhook-Secret` |
| `DOGRAH_ALLOWED_ARTIFACT_HOSTS` | Hosts from which recordings/transcripts may be downloaded (SSRF guard) | No | Comma-separated; checked before any download |
| `DOGRAH_EFFECTIVE_CONCURRENCY` | Concurrency ceiling used by the dialer = min(carrier channels, Dograh org limit) | No | Must be kept equal to Dograh's configured limit (§2.9); set from capacity planning |
| `DOGRAH_REQUEST_TIMEOUT_SECONDS` | HTTP timeout for calls to Dograh | No | Bounded; trigger call is never auto-retried |

Per-campaign values — Agent UUID, chosen telephony configuration, caller-ID number — are **business config** stored on the campaign row, not environment variables (§1).

### 2.3 AI providers (LLM, STT, TTS)

**Inside Dograh** (Providers and Models screens): STT, LLM and TTS provider credentials, model ids, voices and regions for the live call. These are **not** duplicated into Django. The region must match the Dograh deployment region (Infrastructure Architecture §5).

**In Django**, only if post-call analysis calls an LLM directly:

| Variable | Description | Secret? | Notes |
|---|---|---|---|
| `ANALYSIS_LLM_API_KEY` | Credential for the post-call analysis model | Yes | Separate key from the live-call key so cost and revocation are independent; omit if Dograh's QA node is used instead |
| `ANALYSIS_LLM_MODEL_ID` | Model for analysis | No | Distinct from `prompt_template_version` (Database Design §2.3), which is business config; model/version/prompt metadata is persisted with each analysis for reproducibility |

The former variables `STT_PROVIDER_*`, `LLM_PROVIDER_*`, `TTS_PROVIDER_*`, `TELEPHONY_PROVIDER_*` and `TELEPHONY_WEBHOOK_SIGNING_SECRET` are **retired** for the live path.

### 2.4 API / authentication

| Variable | Description | Secret? | Notes |
|---|---|---|---|
| `JWT_SIGNING_KEY` | Signs/verifies access and refresh tokens (SimpleJWT `SIGNING_KEY`); must differ from `DJANGO_SECRET_KEY` | Yes | Rotate per organizational key-rotation policy |
| `JWT_ACCESS_LIFETIME_SECONDS` | Access-token lifetime | No | `900` (15 min) in Production; refresh tokens rotate on use and are blacklisted after rotation |
| `API_RATE_LIMIT_PER_MINUTE` | Concrete threshold closing Threat Model risk #6 | No | **Must be explicitly set — see §4 below** |
| `WEBHOOK_RATE_LIMIT_PER_MINUTE` | Threshold for webhook ingestion, informed by Load Test Plan §4.3 | No | Set from load-test results, not guessed |

### 2.5 Service-to-service

| Variable | Description | Secret? | Notes |
|---|---|---|---|
| `SERVICE_MESH_TLS_CERT` | Certificate for mutual TLS between internal services (Security Architecture §6) | Yes | |
| `EVENT_BUS_URL` | Connection for the disconnect/reconnect event bus (Infrastructure Architecture §1) | Yes | |
| `CALL_QUEUE_BROKER_URL` | Celery broker (Redis or RabbitMQ) for the Calling Queue (Infrastructure Architecture §3) | Yes | Delays are an optimisation; the durable retry schedule lives in `call_attempt.next_dispatch_at` (Django Backend Design §6) |

### 2.6 Observability

| Variable | Description | Secret? | Notes |
|---|---|---|---|
| `LOG_LEVEL` | Logging verbosity | No | `debug` in Dev, `info` in Staging/Production |
| `METRICS_ENDPOINT` | Where metrics (Infrastructure Architecture §8) are shipped | No | |
| `ALERTING_WEBHOOK_URL` | Where alert conditions (disconnect-rate spike, etc.) notify operations | Yes | Production only, typically |

### 2.7 Feature flags

| Variable | Description | Default |
|---|---|---|
| `ENABLE_RECORDING_CONSENT_DISCLOSURE` | Global default for whether the recording-consent disclosure flow (Recording Consent §3) is active for new campaigns | `true` — disabling requires explicit, logged Admin action per Recording Consent §7 / Security Architecture principle of conservative defaults |
| `ENABLE_OUTPUT_SIDE_GUARDRAIL_VALIDATION` | Whether the output-side guardrail check (Threat Model risk #3 mitigation) is active | `false` until implemented and validated in Staging |

### 2.8 Django application

| Variable | Description | Secret? | Notes |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Settings module per environment | No | `config.settings.prod` in Production; `DEBUG` is never true outside Development |
| `DJANGO_SECRET_KEY` | Django cryptographic signing key | Yes | Unique per environment, never committed |
| `DJANGO_ALLOWED_HOSTS` | Explicit host list | No | No wildcards in Production |
| `CORS_ALLOWED_ORIGINS` | Dashboard origin(s) allowed to call the API | No | Explicit list only |
| `FIELD_ENCRYPTION_KEYS` | Key set for field-level encryption (phone, entities, free text, transcript) | Yes | KMS-backed; supports key rotation (multiple keys, newest first) |
| `PHONE_HMAC_KEY` | Key for the deterministic phone-number blind index used by suppression and dedupe | Yes | Rotating it requires re-computing the index; treat as a planned migration |
| `AXES_FAILURE_LIMIT` | Failed logins before lockout | No | Set deliberately |
| `MFA_REQUIRED_ROLES` | Roles that must enrol in MFA | No | At minimum Admin and Campaign Manager |

### 2.9 Dograh deployment settings (set on the Dograh stack, not on Django)

These come from Dograh's own environment-variable reference. Values below are the project's required production posture.

| Variable | Required value / note |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEPLOYMENT_MODE` | `oss` for self-hosted |
| `AUTH_PROVIDER` | `local`, or `stack` for SSO; Dograh UI is operator-only and not exposed publicly without VPN/SSO |
| `ENABLE_SIGNUP` | `false` (invite-only) |
| `OSS_JWT_SECRET` | Strong random value from the secrets manager; never the placeholder |
| `TELEPHONY_WS_TOKEN_SECRET` | Set on **every** process that places or receives calls (API and, if used, Asterisk ARI manager) |
| `TELEPHONY_WS_TOKEN_ENFORCE` | `true` once logs show no `UNVERIFIED media socket` warnings (two-step rollout per Dograh docs). The signed URL appears in access logs, so log access is treated as socket access |
| `DEFAULT_ORG_CONCURRENCY_LIMIT` | Set deliberately to match `DOGRAH_EFFECTIVE_CONCURRENCY` (default is 10) |
| `DATABASE_URL`, `REDIS_URL` | Dograh's **own** PostgreSQL and Redis; Django has no access to them |
| `ENABLE_AWS_S3` + `S3_*` | Use an S3-compatible backend with a **private** bucket and presigned URLs rather than the MinIO backend's public-readable URLs; if MinIO is kept, `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` are strong values |
| `LOG_LEVEL` | `INFO` (default is `DEBUG`) |
| `ENABLE_TELEMETRY` | Set explicitly to `false` |
| `SENTRY_DSN` | Optional; configure PII scrubbing |

---

## 3. Per-environment summary

| Aspect | Development | Staging | Production |
|---|---|---|---|
| Voice runtime (Dograh: telephony/STT/LLM/TTS) | Dograh test mode / web calls and mocked carrier | Separate Dograh instance with sandbox carrier and scriptable calls (Load Test Plan §3) | Production Dograh stack with live provider credentials |
| Database | Local or shared dev instance | Staging instance, production-shaped synthetic data | Production instance, encrypted, backed up |
| Secrets source | Local `.env` acceptable for non-sensitive dev-only values; real secrets still via secrets manager | Secrets manager | Secrets manager, stricter access control |
| Rate limits | Relaxed or disabled | Set to match Production for realistic load testing | Set from Load Test Plan results |
| Monitoring/alerting | Minimal | Full, but alerts not paged to on-call | Full, paged to on-call |

---

## 4. Values that must not be guessed

Two settings are explicitly called out in the Threat Model as needing a deliberate decision rather than an arbitrary default:

- **`API_RATE_LIMIT_PER_MINUTE` and `WEBHOOK_RATE_LIMIT_PER_MINUTE`** (Threat Model risk #6): set from the Load Test Plan's §4.3 outage-shaped flood results, not from an assumed "reasonable" number. Document the source run/date when set.
- **`DOGRAH_EFFECTIVE_CONCURRENCY` / `DEFAULT_ORG_CONCURRENCY_LIMIT`**: derived from the carrier's real channel limit and a load test of the Dograh stack, not from the default of 10.
- **Field-level encryption scope** (Threat Model risk #7): not an environment variable, but a confirmed list of which columns (Database Design) have field-level encryption applied, maintained alongside this document rather than left implicit.

---

## 5. What is deliberately absent from this document

- Retry policy values (max retries, spacing, calling window) — see §1, these are Business config in the `retry_policy` table.
- Agent persona, script skeleton, required entity fields — Business config in `agent_config`.
- Suppression list contents — data, not configuration.

If a value from these categories appears to need an environment variable to "make it work," that's a sign of a design regression against the "configuration without deployment" principle (System Architecture) and should be corrected rather than accommodated.

---

## 6. Traceability

| Config category | Reference |
|---|---|
| Business vs. infrastructure config distinction | System Architecture (configuration without deployment), Database Design §2.2–2.3 |
| Secrets handling | Security Architecture §5 |
| Rate limit sourcing | Threat Model risk #6, Load Test Plan §4.3 |
| Deployment-time checklist usage | Deployment Guide §2 |

---

*No lost conversations. More opportunities. Higher conversion.*
