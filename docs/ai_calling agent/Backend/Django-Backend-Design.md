# AI Calling Agent — Django Backend Design

Complete outbound calling workflow, with disconnect recovery · v1.1 · Status: Draft for review

**Related documents:** Dograh Integration · Database Design · API Specification · Webhook Specification · Security Architecture · Environment Configuration · Call State Machine

**Purpose:** this document replaces the earlier NestJS/TypeScript backend assumption. Django (with Django REST Framework) is the backend framework for authentication, campaigns, contacts, the dialer, webhook ingestion, recovery, post-call analysis and the dashboard API. Because the AI analysis workers were already Python, the whole backend is now one language and one codebase.

---

## 1. Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | Django 5.x LTS line + Django REST Framework | Mature auth, ORM, migrations, admin, security middleware |
| API schema | `drf-spectacular` generating OpenAPI; `API-Specification.yaml` stays the contract and CI checks the two agree | Contract-first |
| Auth | Django auth + `djangorestframework-simplejwt` (short-lived access, rotating refresh with blacklist) | See §4 |
| Database | PostgreSQL (psycopg 3) | System of record, unchanged |
| Async jobs | Celery with Redis or RabbitMQ as broker | Replaces BullMQ (Node-only) |
| Scheduler | Celery beat (dispatcher, reconciler, retention sweeper) | See §6 |
| Cache / locks / rate limits | Redis | Unchanged |
| Realtime dashboard | Server-Sent Events or Django Channels over ASGI (optional) | Live dashboard only — **not** the audio path |
| Object storage | S3 (private bucket) via `boto3` / `django-storages` | Recordings |
| Server | Gunicorn + Uvicorn workers (ASGI) behind ALB/nginx | |
| Frontend | Next.js + TypeScript (unchanged) | Talks to Django over HTTPS |

Django never handles live audio. Dograh owns the voice path (Dograh Integration §2), so no WebSocket media server is needed in Django.

---

## 2. Project layout

```
backend/
  config/                 settings (base / dev / staging / prod), urls, asgi, celery
  apps/
    accounts/             users, roles (Groups), MFA, token endpoints, API-key model for machine clients
    contacts/             import, validation, dedupe, encrypted phone + blind index
    campaigns/            campaign, retry_policy, agent_config (+ Dograh workflow sync)
    suppression/          single canonical DNC / opt-out table and check service
    dialer/               queue admission, eligibility, rate/concurrency control, dispatcher
    voice_runtime/        VoiceRuntime protocol + DograhClient (the only module that talks to Dograh)
    webhooks/             Dograh webhook ingestion, receipts (idempotency), authentication class
    calls/                call_attempt, state machine, disconnect events, transcripts, recordings
    recovery/             State Saver, retry decision, reconnect
    analysis/             post-call analysis, lead scoring, final_output
    dashboard_api/        read-model endpoints, SSE
    audit/                append-only audit events
    core/                 crypto helpers, permissions, throttles, logging redaction, health
  tests/
```

`voice_runtime` exposes a small interface so the platform is not welded to Dograh (the earlier design's "provider abstraction" principle is kept):

```python
class VoiceRuntime(Protocol):
    def start_call(self, req: StartCallRequest) -> StartedCall: ...
    def get_run(self, run_id: str) -> RunResult: ...
    def download_artifact(self, url: str, dest: ObjectRef) -> None: ...
```

`DograhClient` is the only implementation today.

---

## 3. Mapping to the existing data model

Database Design tables map one-to-one to Django models (app in brackets). Additions required by this design:

| Addition | Purpose |
|---|---|
| `contact.phone_encrypted` + `contact.phone_hmac` | Field-level encryption plus a deterministic keyed hash (HMAC-SHA256, key in the secrets manager) so suppression and dedupe lookups work without storing plaintext numbers. Encrypted columns cannot be searched, so **all lookups use `phone_hmac`**. |
| `suppression.phone_hmac` | Same blind index; suppression is matched by number as well as contact id (Database Design §2.12) |
| `call_attempt.provider` / `provider_run_id` | Dograh `workflow_run_id`; unique together |
| `call_attempt.next_dispatch_at` | Durable retry schedule (§6) |
| `webhook_receipt` | `(provider, run_id, event_type)` unique — idempotency record, written before any state change |
| `api_client` | Machine clients that call our API (hashed key, scopes, last-used, revoked-at) |
| `audit_event` | Append-only; actor, action, object, before/after, timestamp, source IP |

Field-level encryption (e.g. a Fernet-based field library or envelope encryption with a KMS data key) applies to: phone numbers, captured entities, free-text feedback, transcript text. The confirmed column list is maintained in Environment Configuration §4 (Threat Model risk #7).

---

## 4. Authentication and authorization — every surface

### 4.1 Human users (dashboard)
- Django `User` with **Argon2** password hashing (`argon2-cffi`), Django's password validators enabled, minimum length 12.
- **MFA required for Admin and Campaign Manager** (TOTP through `django-otp` or `django-allauth` MFA). Sales/Follow-up may be required by policy.
- Brute-force protection with `django-axes` (lockout per user + IP), plus API throttling.
- SimpleJWT: access token lifetime **15 minutes**, refresh token **rotated on every use** with blacklist-after-rotation (`rest_framework_simplejwt.token_blacklist` installed). Logout blacklists the refresh token.
- Tokens are delivered as **httpOnly, Secure, SameSite=Lax/Strict cookies** through a small custom authentication class (or `dj-rest-auth`), so JavaScript — and therefore XSS — cannot read them. When cookies are used, CSRF protection stays enabled for unsafe methods.
- The Django admin site is disabled in production, or reachable only over VPN/IP allowlist with MFA.

### 4.2 Authorization (RBAC + object level)
Roles are Django Groups with explicit permissions, matching Security Architecture §3: Campaign Manager, Admin, Sales/Follow-up, System.

- **Default deny:** `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = ["rest_framework.permissions.IsAuthenticated"]` plus a project permission class that requires an explicit role mapping per view. A view without a declared permission fails a CI test.
- **Object-level scoping:** every queryset goes through `Model.objects.for_user(user)`; a Campaign Manager can only see their own campaigns' contacts, attempts and analytics. Cross-campaign analytics, retry-policy and agent-config writes, and suppression management are Admin-only.
- Recordings and transcripts need an additional `recordings.listen` permission, are served by short-lived signed URLs, and each access writes an `audit_event`.
- Service accounts (Celery workers, reconciler) use separate database roles with only the privileges they need; no worker role can modify `retry_policy` or `agent_config`.

### 4.3 Machine clients and internal calls
- Outbound to Dograh: `X-API-Key`, key kept in the secrets manager and injected as an environment variable at deploy time.
- Inbound webhooks from Dograh: `DograhWebhookAuthentication` (§5) — not JWT.
- Any other machine caller of our API (CRM export, etc.): `api_client` keys — stored **hashed**, shown once, scoped, revocable, rate-limited.
- Service-to-service inside the cluster: mutual TLS or short-lived service tokens; no shared long-lived keys (Security Architecture §2).

### 4.4 Django security settings (production)
```python
DEBUG = False
ALLOWED_HOSTS = [...]                       # explicit
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher", ...]
CORS_ALLOWED_ORIGINS = [...]               # explicit dashboard origin only
```
CI runs `python manage.py check --deploy`, `bandit`, `pip-audit`, and fails the build on findings above an agreed threshold. Dependencies are pinned and updated through automated PRs.

### 4.5 Rate limiting
DRF throttles (`ScopedRateThrottle`) per scope: `login`, `api-user`, `api-client`, `webhook`. Values come from `API_RATE_LIMIT_PER_MINUTE` and `WEBHOOK_RATE_LIMIT_PER_MINUTE` (Environment Configuration §2.4) and must be set from load-test results. A WAF/rate limit at the edge sits in front of both.

---

## 5. Webhook ingestion (Django side)

Full protocol: Webhook Specification §4A. Reference implementation shape:

```python
import hmac
from django.conf import settings
from rest_framework import authentication, exceptions, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

class DograhWebhookAuthentication(authentication.BaseAuthentication):
    header = "HTTP_X_DOGRAH_WEBHOOK_SECRET"          # header name configured in the Dograh credential

    def authenticate(self, request):
        supplied = request.META.get(self.header, "")
        # current secret and, during rotation only, the previous one
        for secret in filter(None, (settings.DOGRAH_WEBHOOK_SECRET,
                                    settings.DOGRAH_WEBHOOK_SECRET_PREVIOUS)):
            if hmac.compare_digest(supplied.encode(), secret.encode()):
                return (WebhookPrincipal(), None)
        audit_security_event("webhook_auth_failed", request)   # high-visibility log, never the secret
        raise exceptions.AuthenticationFailed("invalid webhook credential")

    def authenticate_header(self, request):
        return "X-Dograh-Webhook-Secret"                       # makes DRF answer 401, not 403


class RunResultSerializer(serializers.Serializer):
    attempt_id = serializers.UUIDField()
    run_id = serializers.CharField(max_length=64)
    call_status = serializers.CharField(max_length=64, allow_blank=True)
    call_disposition = serializers.CharField(max_length=128, allow_blank=True)
    # extra fields ignored; recording/transcript URLs are not trusted or stored here


class DograhRunWebhook(APIView):
    authentication_classes = [DograhWebhookAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def post(self, request):
        data = RunResultSerializer(data=request.data)
        data.is_valid(raise_exception=True)                     # 422-style rejection, never guess
        receipt, created = WebhookReceipt.objects.get_or_create(
            provider="dograh", run_id=data.validated_data["run_id"], event_type="run_completed",
            defaults={"payload_hash": sha256(request.body)},
        )                                                       # durable BEFORE acknowledging
        if created:
            process_run_result.delay(receipt.pk)               # Celery task pulls the run from Dograh and applies it
        return Response(status=status.HTTP_200_OK)
```

The Celery task is the trust boundary: it fetches the authoritative run from Dograh with the API key, checks that the run belongs to the claimed `attempt_id`, then applies the state transition. The webhook body is a notification, not evidence.

If the view returns an error, Django must return a non-2xx only for conditions where a retry helps (`5xx`); validation and authentication failures are final (`401`/`422`), as in Webhook Specification §7.

---

## 6. Dialer, queue and retries

- **Claiming work:** the dispatcher selects due attempts with `SELECT … FOR UPDATE SKIP LOCKED` inside a transaction and marks them `DISPATCHING`; two workers can never claim the same attempt.
- **Durable schedule:** every future retry is stored as `call_attempt.next_dispatch_at` (30 seconds, then 10 minutes by default per Database Design §2.2). The database is the source of truth; broker countdowns are only an optimisation. With a Redis broker, long ETA tasks interact badly with the visibility timeout, so the beat-driven dispatcher — not in-memory ETA tasks — guarantees nothing is lost.
- **Admission checks at dial time**, not just at enqueue: campaign active, calling window, suppression by `phone_hmac` and contact id, concurrency permit.
- **Concurrency/rate control:** Redis-based semaphore keyed by Dograh organization/carrier, limit = the minimum of carrier channels and Dograh's configured org concurrency (Dograh Integration §7).
- **Celery configuration:** `acks_late=True`, `reject_on_worker_lost=True`, task time limits, separate queues (`dial`, `webhook`, `recovery`, `analysis`, `default`) so an analysis backlog cannot starve dialing. All tasks are idempotent.
- **State transitions** go through one service function that opens a transaction, locks the `call_attempt` row, checks the allowed-transition table from the Call State Machine, and refuses to move a terminal attempt (for example `EndedNormally` cannot become `DroppedMidCall`; anomalies are logged, not hidden).
- **Reconciler (beat):** resolves stuck `DIALING`/`IN_CALL` attempts by pulling the Dograh run (Dograh Integration §5.4).
- **Retention sweeper (beat):** deletes expired recordings, transcripts and working memory from the DB and object storage, never touching `suppression`.

---

## 7. Logging, audit and privacy

- Structured JSON logs with `call_id`, `attempt_id`, `campaign_id`, `provider_run_id`, `trace_id`.
- A logging filter redacts known secret-shaped fields, `Authorization`, `Cookie`, the webhook header, `X-API-Key`, and any URL query token; phone numbers are masked in logs.
- `audit_event` is append-only; the application database role has `INSERT` only on it. Written for every change to `retry_policy`, `agent_config`, `suppression`, role assignments, API clients, and every human access to a recording or transcript.
- Django `DEBUG` stays off; error pages never show settings or request bodies; Sentry is configured with PII scrubbing.

---

## 8. Testing additions

| Area | Test |
|---|---|
| Webhook auth | Missing, wrong and previous-secret headers (TC-DG.01–03); constant-time compare path covered |
| Verify-by-pull | Webhook claims an outcome that Dograh's run does not confirm → rejected, alert raised (TC-DG.04) |
| Idempotency | Same `run_id` posted twice → one transition (TC-WH.04 updated) |
| RBAC | Every endpoint × every role matrix; Campaign Manager cannot read another manager's campaign; default-deny test fails any view without declared permissions |
| Dial safety | Crash between Dograh trigger and `provider_run_id` write does not cause a second call; suppression added during the wait blocks the retry |
| Reconciler | Lost webhook is recovered by the sweeper (TC-DG.05) |
| Secrets | Log-capture test proves secrets and recording URLs never appear in logs |

---

## 9. Implementation order

1. Project skeleton, settings split, CI (`check --deploy`, bandit, pip-audit), PostgreSQL, Celery.
2. `accounts` (users, roles, MFA, JWT cookies, throttling, axes) and `audit`.
3. `contacts`, `suppression` (encrypted phone + blind index), `campaigns`.
4. `voice_runtime.DograhClient` against a Dograh sandbox; workflow sync from `agent_config`.
5. `dialer` + `calls` state machine + `webhooks` + reconciler.
6. `recovery`, then `analysis`, then `dashboard_api`.
7. Hardening: load tests including webhook floods, security tests, runbooks.

---

*No lost conversations. More opportunities. Higher conversion.*
