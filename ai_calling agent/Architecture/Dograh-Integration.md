# AI Calling Agent — Dograh Integration (Voice Provider Layer)

Complete outbound calling workflow, with disconnect recovery · v1.1 · Status: Draft for review

**Related documents:** System Architecture · Infrastructure Architecture · Webhook Specification · Security Architecture · Django Backend Design · Environment Configuration

**Purpose:** Dograh is the single provider layer for the live voice path — telephony, STT, LLM, TTS and the post-call webhook. This document defines what Dograh owns, what the Django backend owns, how the two talk to each other, and how every hop is authenticated.

Sources for Dograh behaviour: docs.dograh.com (API reference, Webhook Payloads, Telephony Webhooks, Model Configurations, Environment Variables). Items not confirmed in those docs are marked **[verify]**.

---

## 1. What Dograh is (and what it is not)

Dograh is an open-source (BSD-2), self-hostable voice-agent platform — a visual workflow builder plus a runtime that connects a telephony carrier, an STT service, an LLM and a TTS service into a real-time call. It is built on FastAPI, uses PostgreSQL and Redis, and stores audio in MinIO or S3.

It is **not** a campaign/CRM system for this project. Contacts, suppression, calling windows, retry policy, the call state machine, analytics and the admin dashboard remain in the Django backend (the system of record). Dograh is the *voice runtime* the backend drives.

---

## 2. Responsibility split

| Concern | Owner | Notes |
|---|---|---|
| Contacts, import, dedupe, validation | **Django** | Unchanged from FRS FR-1.1–1.4 |
| Suppression / DNC (Database Design §2.12) | **Django** | Checked before queue entry **and** immediately before every dial call to Dograh, including retries |
| Calling window, retry policy, call state machine | **Django** | Retry decisions are never delegated to Dograh or the LLM |
| Campaign scheduling, rate and concurrency control | **Django** | Must respect Dograh's per-org concurrency limit (§7) |
| Placing the call, carrier signalling | **Dograh** (via its telephony configuration) | Carrier chosen per Dograh Telephony Configuration |
| Live audio streaming, turn-taking, interruption handling | **Dograh** | Django never touches live audio |
| STT, LLM, TTS (live conversation) | **Dograh** (Provider Connections + Named Model Configuration) | Modes: Dograh-managed, BYOK, or Realtime speech-to-speech |
| In-call script, persona, guardrails prompt | **Dograh workflow**, generated from Django `agent_config` | Django is the source of truth; see §4.3 |
| Post-call webhook | **Dograh** sends → **Django** receives | See Webhook Specification §4A |
| Recording and transcript capture | **Dograh** produces → **Django** copies into its own private storage | See §6 |
| Post-call analysis, lead scoring, final output | **Django workers** | Python analysis workers, unchanged logic |
| Dashboard, RBAC, audit | **Django** | |

**Decision recorded:** Dograh's built-in *Campaigns* feature is **not used**. Running two campaign engines would create two sources of truth for suppression and retries, which is a compliance risk. Django owns campaigns; Dograh only receives one "start this call" request per attempt. Revisit only if there is a strong reason to move dialing into Dograh.

---

## 3. Component mapping (System Architecture → implementation)

| System Architecture component | Implemented by |
|---|---|
| 3.1 Contact Database | Django app `contacts` + PostgreSQL |
| 3.2 Calling Queue | Django app `dialer` (PostgreSQL-scheduled, Celery-dispatched) |
| 3.3 Telephony Provider | Carrier configured **inside Dograh** (Twilio, Vonage, Plivo, Telnyx, Cloudonix, Exotel, Vobiz, Asterisk ARI or Dograh Managed SIP) |
| 3.4 Conversation Orchestrator | **Dograh** run (one workflow run per call attempt) |
| 3.5 STT | **Dograh** transcriber setting |
| 3.6 Language Model + Memory | **Dograh** LLM setting + workflow context (`initial_context`, `gathered_context`) |
| 3.7 TTS | **Dograh** voice setting |
| 3.8 Disconnect Detector | Django — derived from the run outcome (see §5.3) |
| 3.9 State Saver | Django — persists transcript, recording, gathered context, status |
| 3.10 Retry Policy Engine | Django `dialer.retry` |
| 3.11 Reconnect Manager | Django — new Dograh run seeded with saved context |
| 3.12 Post-Call Analysis | Django Celery workers |
| 3.13–3.15 Data stores, dashboard, final output | Django + PostgreSQL + private S3 bucket |

---

## 4. Integration contract

### 4.1 Outbound: Django → Dograh (start a call)

`POST {DOGRAH_BASE_URL}/api/v1/public/agent/workflow/{workflow_uuid}`
Header: `X-API-Key: <Dograh API key>`

Body fields used:

| Field | Value |
|---|---|
| `phone_number` | Contact number in E.164, decrypted only at call time |
| `initial_context` | Must include our `attempt_id`, `campaign_id`, `contact_ref` (opaque id, not PII), and any prompt variables |
| `telephony_configuration_id` | Optional — routes through a specific carrier configuration |
| `from_phone_number_id` | Optional — pins the caller ID |
| `model_overrides` | Optional — per-call override of LLM / STT / TTS (by named configuration UUID or provider connection) |

Response: `workflow_run_id` — stored on `call_attempt.provider_run_id` **before** the dial job is acknowledged.

**Idempotency:** Django's `idempotency_key = campaign_id + contact_id + attempt_id` is enforced on our side — a unique constraint on `call_attempt` plus a "dial already issued" check. The Dograh trigger endpoint is not documented as idempotent, so a worker crash between the HTTP call and persisting `provider_run_id` must be handled by the reconciler (§5.4), which looks for runs carrying our `attempt_id` in `initial_context`. **[verify]** whether the run-listing API can filter by an `initial_context` value; if not, persist a `DIAL_REQUESTED` row before the call and treat it as "unknown outcome → reconcile" rather than redialing.

### 4.2 Inbound: Dograh → Django (post-call webhook)

A `webhook` node at the end of the workflow posts the run result to Django after the run completes. The payload template carries our correlation ids:

```json
{
  "attempt_id": "{{initial_context.attempt_id}}",
  "campaign_id": "{{initial_context.campaign_id}}",
  "run_id": "{{workflow_run_id}}",
  "call_status": "{{gathered_context.call_status}}",
  "call_disposition": "{{gathered_context.call_disposition}}",
  "duration_seconds": "{{cost_info.call_duration_seconds}}",
  "recording_url": "{{recording_url}}",
  "transcript_url": "{{transcript_url}}"
}
```

Authentication, replay handling and trust model: Webhook Specification §4A.

### 4.3 Agent configuration sync

`agent_config` (Database Design §2.3) remains the business source of truth. A Django service renders it into a Dograh workflow definition and pushes it through the Dograh Agents API (create from definition / update), then publishes. Rules:

- Only a service account with Admin-approved changes may push; every push is audit-logged with before/after (Security Architecture §9).
- The pushed workflow's Agent UUID is stored on the campaign; calls always target a **published** version.
- The compliance/consent opening and the opt-out handling are part of the generated workflow and cannot be removed by editing `agent_config` free text.

### 4.4 Model configuration (LLM, STT, TTS)

Configured in Dograh under **Providers** (credentials) and **Models** (named configurations), then selected as the organization default or per agent. Dograh offers three modes: *Dograh* (one managed connection for LLM/STT/TTS/embeddings), *BYOK* (separate external providers for each service) and *Realtime* (external speech-to-speech model plus a separate LLM for extraction/QA).

Project rules:

- **Production uses BYOK or Dograh mode with keys owned by the organization**, never a developer's personal key.
- Provider keys live in Dograh's provider connection store (saved secrets are not returned to the browser). They are **not** duplicated into Django — Django only holds the *named configuration UUID* it passes in `model_overrides`.
- External providers receive prompts, conversation history, transcripts and audio. Provider retention, training and regional-hosting terms must be reviewed and recorded before go-live (Data Privacy doc). Choose providers and regions so that STT, LLM and TTS sit in the same region as the Dograh deployment (Infrastructure Architecture §5).
- Specific vendors (for example which STT, LLM or TTS) are a configuration choice made inside Dograh and do not change this architecture.

---

## 5. Call lifecycle with Dograh

### 5.1 Happy path
1. Django dispatcher selects an eligible attempt, re-checks suppression, calling window and campaign status.
2. Django calls Dograh trigger endpoint → stores `provider_run_id`, sets attempt `DIALING`.
3. Dograh dials via its carrier; conversation runs (STT → LLM → TTS) inside Dograh.
4. Run ends → Dograh webhook node posts to Django.
5. Django authenticates the request, **verifies the run by pulling it from Dograh** (§ Webhook Spec 4A.3), applies the state transition, copies recording and transcript to private storage, enqueues post-call analysis.

### 5.2 Never-connected failures
Dograh normalises carrier statuses into `initiated`, `ringing`, `in-progress`, `answered`, `completed`, `busy`, `no-answer`, `canceled`, `failed`, `error`. Django maps the run's final status to the Call State Machine's `ConnectionFailureReason` set:

| Dograh final status | Django classification |
|---|---|
| `busy` | `busy` |
| `no-answer` | `no_answer` |
| `failed`, `error` | `provider_error` or `network_error` — refine from run detail **[verify]** |
| `canceled` | `rejected` only if the carrier reason says so; otherwise treated as `provider_error` — conservative, requires review |
| invalid-number outcomes | `invalid_number` — carrier-specific, **[verify]** per chosen carrier |

The mapping table is code-owned and covered by tests; unknown statuses default to `provider_error` and raise an alert rather than being silently dropped.

### 5.3 Mid-call disconnects — important difference from the original design
The original design assumed the telephony provider pushes real-time `call.disconnected` events to our platform. With Dograh, carrier callbacks terminate at **Dograh**, and the documented hook into our system is the **post-run webhook**. Consequences:

- Django learns about a mid-call drop **when the run ends**, not while it is happening. The recovery flow (save state → classify → retry decision → reconnect) therefore starts from the run-ended notification and the run's `call_status` / `call_disposition`.
- The State Saver's "persist before retry decision" invariant still holds: Django persists transcript, recording and gathered context first, then evaluates retry.
- Reconnect is implemented as a **new Dograh run** for the same contact whose `initial_context` carries the saved conversation summary/memory, not as resuming the old session.
- If sub-second visibility into drops is required, evaluate Dograh's call events export or a custom hook **[verify]**; do not assume it exists.

### 5.4 Reconciliation (no lost conversations)
Dograh's webhook node does not retry non-200 responses by default; delivery retry must be enabled through the node's `retry_config`. Even with retries, webhooks can be lost, so Django runs a **reconciler** (Celery beat): any attempt in `DIALING` or `IN_CALL` longer than a configured ceiling (call timeout + margin) is resolved by pulling the run from Dograh and feeding it through the same handler as the webhook. This is what preserves the "no lost conversations" guarantee at the Dograh boundary.

---

## 6. Recordings and transcripts

Dograh exposes recording and transcript through download URLs that are described as public and time-limited. Treat every such URL as a **bearer credential**:

- Django downloads them **server-side, immediately**, over TLS, into the project's private object-storage bucket (encrypted at rest, no public ACL).
- URLs are never written to logs, never stored long-term, never returned to browsers.
- Humans access recordings only through Django-issued, short-lived signed URLs after an RBAC check, and each access is audit-logged (Security Architecture §9).
- Dograh's own storage (MinIO/S3) follows the retention policy too; use an S3-compatible backend with presigned URLs and a **private** bucket rather than the MinIO backend's anonymously readable URLs.

---

## 7. Capacity and limits

Three independent ceilings apply; the effective concurrency is the minimum:

1. **Carrier** — channel limits and calls-per-second on the chosen account.
2. **Dograh organization concurrency** — `DEFAULT_ORG_CONCURRENCY_LIMIT` defaults to 10 concurrent calls per organization; production must set it deliberately.
3. **Dograh server capacity** — the FastAPI workers behind nginx, per Dograh's scaling guidance.

Django's rate and concurrency controller reads the configured effective limit and applies backpressure (jobs wait in the queue) rather than sending calls Dograh will reject. Load-test plan §3 gains a scenario for Dograh saturation.

---

## 8. Deployment topology

- **Self-hosted Dograh in the same VPC and region** as Django is the recommended default: PII, recordings and transcripts stay inside the project's boundary, and latency to STT/LLM/TTS is controlled.
- Dograh's own services (API, UI, PostgreSQL, Redis, storage, optional TURN) are separate deployables with their **own** database — Django never reads or writes Dograh's database. The only integration surface is the HTTPS API and the webhook.
- Dograh UI is for operators only: not internet-exposed without SSO/VPN, signup disabled (`ENABLE_SIGNUP=false`), strong `OSS_JWT_SECRET`.
- Hosted Dograh Cloud is an alternative; if chosen, add a data-processing review, since recordings and transcripts then live at a third party.

---

## 9. Authentication summary for this integration

| Hop | Mechanism |
|---|---|
| Django → Dograh API | `X-API-Key` (organization-scoped key, dedicated to the backend), TLS, source-IP restricted at Dograh's proxy |
| Dograh → Django webhook | Stored credential header (secret), network allowlist or mTLS at the edge, plus verify-by-pull |
| Carrier → Dograh | Provider signature verification inside Dograh (Twilio HMAC-SHA1, Plivo/Vobiz HMAC-SHA256, Vonage JWT); other carriers **[verify]** before selection |
| Carrier → Dograh media WebSocket | `TELEPHONY_WS_TOKEN_SECRET` signed URL with `TELEPHONY_WS_TOKEN_ENFORCE=true` |
| Operators → Dograh UI | Local auth with signup disabled, or Stack Auth SSO; behind VPN |
| Users → Django | JWT with short expiry, MFA for Admin (Django Backend Design §4) |

Known limitation: Dograh API keys are scoped to the organization, not to individual operations. Mitigate with a dedicated key for the backend, network restriction, rotation (archive/reactivate) and monitoring of key usage.

---

*No lost conversations. More opportunities. Higher conversion.*
