# AI Calling Agent — Security Architecture

Complete outbound calling workflow, with disconnect recovery · v1.1 · Status: Draft for review (Dograh + Django update)

**Related documents:** Infrastructure Architecture v1.0 · API Specification v1.0 · Webhook Specification v1.0 · Memory Specification v1.0 · Database Design v1.0 · AI Agent Specification v1.0

**Purpose:** security requirements are referenced across several documents — encryption and secrets (Infrastructure Architecture §7), signature verification (Webhook Specification §4), retention (Memory Specification §9), suppression (Database Design §2.12), and compliance guardrails (AI Agent Specification §8). This document consolidates them into a single security architecture and adds what wasn't yet specified: authentication/authorization, data classification, threat model, audit logging, and incident response.

---

## 1. Data classification

| Class | Examples | Handling requirement |
|---|---|---|
| **Restricted (PII)** | Phone numbers, call recordings, transcripts, captured entities (name, preferences), suppression records | Encrypted at rest and in transit; access logged; retained only per policy (§7) |
| **Confidential (business)** | Campaign scripts, retry policy config, lead scores, analytics | Encrypted at rest; access role-restricted (§3) |
| **Internal** | System logs, metrics, non-PII operational data | Standard access controls, no special handling |
| **Secret** | Provider API keys, signing secrets, database credentials | Secrets manager / KMS only; never in code, config files, or logs |

Every table in the Database Design document falls into Restricted or Confidential; none is Internal-only, since even `campaign` and `retry_policy` rows are tied to identifiable contacts once joined.

---

## 2. Authentication — every surface is authenticated

**Rule:** no endpoint, queue, socket, storage object or operator console is reachable without a verified identity. "Internal" is not a trust level. Backend framework: Django + DRF (Django Backend Design §4).

| # | Surface | Who calls it | Mechanism | Also required |
|---|---|---|---|---|
| 1 | Dashboard / REST API | Staff users | Django auth, Argon2 passwords, **MFA** (Admin, Campaign Manager), JWT access token (15 min) + rotating refresh with blacklist, delivered as httpOnly Secure cookies | Brute-force lockout, throttling, CSRF protection for cookie auth |
| 2 | Django admin site | Admins | Disabled in production, or VPN/IP allowlist + MFA | Audit logging |
| 3 | Machine clients of our API | CRM/export jobs | Hashed, scoped, revocable `api_client` keys | Per-key rate limit, last-used tracking |
| 4 | Webhook `/webhooks/dograh/run-completed` | Dograh | Shared-secret header (constant-time, dual-secret rotation) | Network allowlist or mTLS, TLS, **verify-by-pull**, idempotency receipt (Webhook Specification §4A) |
| 5 | Django → Dograh API | Backend | `X-API-Key` (dedicated, organization-scoped), TLS, source-IP restriction | Key in secrets manager; rotation by archive/replace |
| 6 | Carrier → Dograh answer/status webhooks | Carrier | Provider signature verification inside Dograh (Twilio HMAC-SHA1, Plivo/Vobiz HMAC-SHA256, Vonage JWT); other carriers **[verify]** before selection | Dograh served only over HTTPS |
| 7 | Carrier → Dograh media WebSocket | Carrier | Signed URL: `TELEPHONY_WS_TOKEN_SECRET` with `TELEPHONY_WS_TOKEN_ENFORCE=true` | Log access restricted — the token appears in access logs |
| 8 | Dograh operator UI | Operators | Local auth with signup disabled, or Stack Auth SSO | VPN only, strong `OSS_JWT_SECRET` |
| 9 | Dograh → STT / LLM / TTS providers | Dograh | Provider API keys held in Dograh's provider connections | Keys owned by the organization; provider data terms reviewed |
| 10 | Service-to-service inside the platform | Workers, API, Dograh | Mutual TLS or short-lived service tokens; separate DB roles per service | No shared long-lived keys |
| 11 | Recording / transcript access | Users | Short-lived signed URLs issued after an RBAC check | Every access audit-logged; artifacts live in a private bucket |
| 12 | Database, Redis, broker, object storage | Services only | Per-service credentials, TLS, private subnets, no public endpoints | Encryption at rest |
| 13 | Live dashboard stream (SSE/WebSocket) | Staff users | Same token as the REST API, validated at connection time and on expiry | Authorization re-checked per subscription |

JWTs carry subject, role and expiry; refresh tokens are single-use. Dograh API keys are scoped to the organization only (no per-operation scopes), which is why items 4 and 5 add network restriction, rotation and monitoring on top of the key.

---

## 3. Authorization — role-based access control

| Role | Permissions |
|---|---|
| **Campaign Manager** | Create/view campaigns, import contacts, view contact/attempt data and analytics for their own campaigns |
| **Admin** | All Campaign Manager permissions, plus: configure retry policy (`FR-3.6`), configure agent config, view/manage suppression list, view cross-campaign analytics |
| **Sales / Follow-up** | Read-only access to Final Output records and contact views; no access to raw recordings unless explicitly granted |
| **System (service accounts)** | Scoped exactly to the operations each component needs — e.g. the State Saver can write `working_memory_snapshot` but has no route to modify `retry_policy` |

**Principle:** no role or service account has broader access than its function requires. In particular, the distinction between *reading* campaign status (widely available) and *writing* retry-policy configuration (Admin-only) mirrors the FRS's own separation of FR-3.5 (dashboard display) from FR-3.6 (dashboard configuration).

---

## 4. Encryption

- **At rest:** Primary DB, Object Storage (recordings), and the In-memory Store's durable backing are all encrypted at rest, per Infrastructure Architecture §7.
- **In transit:** all service-to-service and client-to-service traffic uses TLS; this includes calls to the telephony provider, STT, LLM, and TTS services.
- **Field-level consideration:** phone numbers and any free-text fields likely to contain PII (e.g. `free_text_feedback`, transcript content) are candidates for field-level encryption in addition to at-rest disk encryption, so that a database-level compromise doesn't expose raw PII without an additional key.

---

## 5. Secrets management

- All credentials in the Secret classification (§1) live in a secrets manager / KMS (Infrastructure Architecture §7).
- Signing secrets used for webhook verification (Webhook Specification §4) are rotatable without downtime — the system should support validating against both a current and a short-lived previous secret during rotation, so a rotation event doesn't reject legitimate in-flight webhook deliveries.
- Dograh-specific secrets: `DOGRAH_API_KEY`, `DOGRAH_WEBHOOK_SECRET` (+ previous during rotation), `OSS_JWT_SECRET`, `TELEPHONY_WS_TOKEN_SECRET`, and the STT/LLM/TTS keys inside Dograh. Dograh shows a new API key only once, so it goes straight into the secrets manager; saved provider secrets are not returned to the browser.
- Secrets are never written to application logs; log redaction rules should explicitly scrub known secret-shaped fields as a defense-in-depth measure, not rely solely on developers remembering not to log them.

---

## 6. Network security

- The Conversation Orchestrator, STT, LLM, and TTS services communicate within a private network boundary; only the API Gateway and webhook ingestion endpoints are internet-facing (consistent with Infrastructure Architecture §1's topology).
- The Admin Dashboard's write endpoints (retry policy, agent config) should be reachable only through authenticated, rate-limited API paths — not exposed as unauthenticated internal endpoints reachable from the same network as less-trusted services.
- Webhook endpoints, while internet-facing or reachable from Dograh, are the highest-risk ingress point precisely because they are verified by a shared secret rather than a user session; they are isolated behind a network allowlist or mTLS, rate limiting and anomaly detection separate from the authenticated API surface.
- **Dograh is a separate trust zone.** A self-hosted Dograh stack runs in its own subnet with its own database and Redis; Django has no credentials to those stores, and Dograh has no credentials to the Django database. The only integration surfaces are the Dograh HTTPS API and the webhook. The Dograh UI is not reachable from the internet without VPN/SSO.

---

## 7. Data retention & the right to be forgotten

Extending Memory Specification §9:

- Recordings, transcripts, and working memory follow a configurable retention window; once expired, they are deleted, not merely archived, from the Primary DB and Object Storage.
- The `suppression` table (Database Design §2.12) is explicitly **exempt** from standard retention expiry — a do-not-call request must be honored indefinitely, independent of how long other call data is kept, since deleting it would reintroduce the compliance risk it exists to prevent.
- A contact-level deletion request (beyond suppression — a full erasure request) should cascade across `contact`, `call_attempt`, `transcript`, `recording_ref`, `analysis`, `contact_history`, and `final_output`, while still preserving a minimal suppression record keyed by phone number so the contact isn't inadvertently re-imported and re-called later.

---

## 8. Compliance guardrails carried from the AI Agent

The AI Agent Specification (§8) defines in-call compliance behavior; this section states the corresponding system-level enforcement:

- A `requires_suppression = true` output (Prompt Specification §4) must propagate to the `suppression` table within the same processing pipeline that saves the call's other data — it must not be a best-effort, eventually-consistent side effect that could be lost.
- Calling-window enforcement (`FR-6.6`) is a compliance control, not just a courtesy setting — the Calling Queue must treat it as a hard constraint, not an advisory one.
- Suppression checks (§7) must run against every dial attempt, including retries, not only at initial queue entry — a contact suppressed mid-campaign must not be dialed again by an already-scheduled retry.

---

## 9. Audit logging

- Every write to `retry_policy`, `agent_config`, and `suppression` should be logged with actor (user or service), timestamp, and before/after values — these are the configuration points most likely to need after-the-fact review.
- Every access to a recording or transcript by a human user (not automated post-call analysis) should be logged, since these are the most sensitive Restricted-class artifacts.
- Audit logs themselves are Restricted/Confidential and are retained independently of the operational data they describe, per standard audit-trail practice.

---

## 10. Threat model summary

| Threat | Mitigation |
|---|---|
| Forged webhook events (fake disconnect/connection events) | Signature verification (§2, Webhook Specification §4); reject unsigned/invalid requests |
| Replay of a legitimate webhook | Timestamp freshness check (Webhook Specification §4) |
| Credential/secret leakage | Secrets manager only, log redaction, rotation support (§5) |
| Unauthorized retry-policy or agent-config change | Role-based access control, Admin-only write scope (§3), audit logging (§9) |
| Re-contacting a suppressed number | Suppression check on every dial including retries (§8); suppression checked by phone number as well as contact ID (Database Design §2.12) |
| PII exposure via database compromise | Encryption at rest, field-level encryption for high-sensitivity fields (§4) |
| Prompt injection via contact speech attempting to alter agent behavior | The AI Agent's guardrails (AI Agent Specification §8) and fixed system-prompt structure (Prompt Specification §2) constrain what a contact's utterance can change — user-turn content is data, not instructions, and cannot rewrite the persona, goal, or guardrail sections of the prompt |
| Denial of service via webhook flooding | Rate limiting and anomaly detection at the ingestion boundary (§6) |
| Leaked webhook secret used to forge call outcomes | Verify-by-pull against the Dograh API; network allowlist/mTLS; dual-secret rotation (Webhook Specification §4A) |
| Replay of an old Dograh webhook body | Idempotency receipt + terminal-state guard + verify-by-pull (Dograh sends no signed timestamp) |
| SSRF or malicious download via `recording_url` / `transcript_url` in the payload | Body URLs never fetched; only URLs from the pulled run, host-allowlisted, size/time limited |
| Compromised Dograh API key (organization-scoped, not operation-scoped) | Dedicated key, source-IP restriction, rotation, usage monitoring, alert on unexpected callers |
| Guessable media WebSocket URL (workflow/org/run ids) | `TELEPHONY_WS_TOKEN_SECRET` + `TELEPHONY_WS_TOKEN_ENFORCE=true`; restricted log access |
| Provider-held data (prompts, transcripts, audio sent to STT/LLM/TTS providers) | Provider data-terms review, same-region placement, retention settings recorded before go-live |
| Stolen JWT via XSS | httpOnly Secure cookies, short access lifetime, rotating refresh with blacklist, CSP on the dashboard |
| Duplicate call after crash between trigger and persisting the run id | Unique attempt constraint, `DIAL_REQUESTED` record, reconciler instead of blind redial (Dograh Integration §4.1) |

---

## 11. Incident response notes

- A sustained spike in `call.disconnected` events failing signature verification (Webhook Specification §9) should be treated as a possible secret-rotation failure or active attack, and paged to operations immediately rather than only logged.
- A suspected suppression-list failure (evidence of a suppressed contact being dialed) is treated as a compliance incident, escalated separately from ordinary bugs, given the regulatory exposure involved.
- Any confirmed PII exposure (e.g. a misconfigured access control exposing recordings) triggers the organization's standard data-breach response process, which is outside the scope of this document but must be linked from here once defined.

---

## 12. Traceability

| Security element | Reference |
|---|---|
| Encryption, secrets, network isolation | Infrastructure Architecture §7, Dograh Integration §8–§9 |
| Django authentication, RBAC, throttling | Django Backend Design §4 |
| Webhook authentication (Dograh), verify-by-pull, idempotency | Webhook Specification §4A, §5–§6 |
| Retention, suppression persistence | Memory Specification §9, Database Design §2.12 |
| In-call compliance behavior | AI Agent Specification §8 |
| Prompt-injection resistance | Prompt Specification §2 |

---

*No lost conversations. More opportunities. Higher conversion.*
