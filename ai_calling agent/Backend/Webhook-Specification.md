# AI Calling Agent — Webhook Specification

Complete outbound calling workflow, with disconnect recovery · v1.1 · Status: Draft for review (Dograh update)

**Related documents:** API Specification v1.0 (`/webhooks/*`) · FRS v1.0 · Call State Machine v1.0 · Infrastructure Architecture v1.0

**Purpose:** the API Specification defines the webhook endpoints at a schema level; this document specifies delivery guarantees, signature verification, idempotency, ordering, retry behavior, and the full set of events the telephony provider (and, for one event, the conversation engine itself) sends into the system.


> **v1.1 change — Dograh is now the voice provider layer.** Carrier callbacks terminate at Dograh, not at this system. The only webhook this system receives for call results is Dograh's post-run webhook node. §4A is the **normative** authentication and trust model for production; §4 describes the generic `X-Provider-Signature` scheme and applies only to any future provider that signs requests. §1 event types are now **derived** from the Dograh run result (§4A.4) rather than pushed by a carrier in real time. See Dograh Integration §5.3.

---

## 1. Event types

| Event | Sent by | Triggers | FR reference |
|---|---|---|---|
| `connection.status` | Telephony provider | Stage 1 connected/failed decision | FR-1.6, FR-1.7 |
| `call.disconnected` | Telephony provider | Stage 4 recovery flow | FR-2.8, FR-4.1–FR-4.3 |
| `call.reconnect.result` | Telephony provider | Confirms whether a Reconnect Manager dial attempt succeeded | FR-4.5 |
| `call.ended` | Telephony provider | Normal call termination, triggers post-call analysis | FR-3.1 |

Only `connection.status` and `call.disconnected` are exposed as public endpoints in the API Specification; `call.reconnect.result` and `call.ended` follow the same envelope and verification rules and are documented here for completeness since they use the same delivery infrastructure.

---

## 2. Delivery envelope

Every webhook request shares this envelope, regardless of event type:

```json
{
  "event_id": "evt_9f2c1a...",
  "event_type": "call.disconnected",
  "occurred_at": "2026-09-15T10:22:31Z",
  "attempt_id": "b3e1...",
  "data": { }
}
```

| Field | Description |
|---|---|
| `event_id` | Unique per delivery attempt is **not** guaranteed — see idempotency (§5). Unique per logical event. |
| `event_type` | One of the values in §1 |
| `occurred_at` | When the underlying telephony event actually happened (not when the webhook was sent) |
| `attempt_id` | The call attempt this event relates to |
| `data` | Event-specific payload, see §3 |

---

## 3. Event payloads

### 3.1 `connection.status`
```json
{
  "event_type": "connection.status",
  "attempt_id": "b3e1...",
  "data": {
    "connected": false,
    "failure_reason": "no_answer"
  }
}
```
`failure_reason` is required when `connected = false` and must be one of the values in the Call State Machine's `ConnectionFailureReason` set (`no_answer`, `busy`, `invalid_number`, `rejected`, `network_error`, `provider_error`). Omitted when `connected = true`.

### 3.2 `call.disconnected`
```json
{
  "event_type": "call.disconnected",
  "attempt_id": "b3e1...",
  "data": {
    "disconnect_reason": "network_problem",
    "last_known_duration_seconds": 94
  }
}
```
`disconnect_reason` must be one of `technical_issue`, `network_problem`, `provider_error`, `customer_hangup`, `ai_error`, `unknown` (Call State Machine §2.1). If the provider cannot determine a reason, send `unknown` rather than omitting the field — the State Saver (Memory Specification §3) requires a value to classify against.

### 3.3 `call.reconnect.result`
```json
{
  "event_type": "call.reconnect.result",
  "attempt_id": "b3e1...",
  "data": {
    "reconnected": true
  }
}
```
If `reconnected: false`, this is treated as a new connection failure and re-enters the retry evaluation (Detailed Workflow, Step 4.5 note on reconnect failure).

### 3.4 `call.ended`
```json
{
  "event_type": "call.ended",
  "attempt_id": "b3e1...",
  "data": {
    "ended_reason": "contact_hangup_normal"
  }
}
```
Distinct from `call.disconnected` — this event means the conversation reached a natural end, not an unexpected drop.

---

## 4. Signature verification (generic provider scheme — not used by Dograh)

All webhook requests must be verified before processing; unverified requests must be rejected with `401` and not passed to any downstream handler.

- Verification uses the `X-Provider-Signature` header (API Specification `webhookSignature` security scheme).
- The signature is computed over the raw request body using a shared secret configured per telephony provider integration.
- Requests older than 5 minutes (comparing `occurred_at` or a provider-supplied timestamp header to current time) should be rejected even with a valid signature, to limit replay exposure.
- Signature secrets are stored in the secrets manager (Infrastructure Architecture §7), never in application config.

---

## 4A. Dograh webhook trust model (normative)

### 4A.1 What Dograh provides
- A `webhook` node executes **asynchronously after a run completes** and sends the rendered payload template as JSON (default `POST`) to the configured URL.
- Authentication options on the stored credential: `NONE`, `API_KEY` (custom header), `BEARER_TOKEN`, `BASIC_AUTH`, `CUSTOM_HEADER`. A body signature (HMAC) and a signed timestamp are **not documented** **[verify]**; this specification therefore does not rely on them.
- Non-200 responses are logged but **not retried by default**; retry is enabled through the node's `retry_config`. Duplicate deliveries are possible. The receiver is expected to answer `2xx` within 30 seconds.

### 4A.2 Required controls (all of them, in every non-development environment)
1. **Shared-secret header.** Use the `API_KEY` credential type with a dedicated header (for example `X-Dograh-Webhook-Secret`). `NONE` is forbidden outside development; `BASIC_AUTH` is not used. The secret is at least 32 random bytes, unique per environment, held in the secrets manager, and compared in **constant time** (`hmac.compare_digest`). It supports **dual-secret rotation** (current + previous) so rotation never drops in-flight deliveries (Security Architecture §5).
2. **TLS only.** HTTPS with a valid certificate; the webhook lives on its own path (`/webhooks/dograh/run-completed`) so it can carry its own rate limit and network rules.
3. **Network restriction.** Accept the webhook only from Dograh's egress addresses or private network (security group / allowlist), or require mutual TLS at the reverse proxy. Traffic from any other source is dropped before reaching the application.
4. **Verify-by-pull.** The webhook body is a *notification*, not evidence (§4A.3). A leaked webhook secret alone must not be enough to forge an outcome.
5. **Idempotency record first.** Write a `webhook_receipt` row, unique on `(provider, run_id, event_type)`, before any state change (§5). A duplicate returns `200` without reprocessing.
6. **Replay handling without signed timestamps.** Dograh's `call_time` is the *run creation* time, not the delivery time, so the 5-minute freshness rule of §4 cannot be applied to this webhook. Replay protection is the combination of (a) the idempotency receipt, (b) the state machine's terminal-state guard (a replay cannot change an already-terminal attempt), and (c) verify-by-pull (a replayed body cannot assert something the Dograh run does not confirm).
7. **Untrusted fields.** `recording_url` and `transcript_url` from the request body are **never** fetched. Only URLs from the pulled run are used, and only after checking the host against the configured Dograh/storage allowlist (SSRF protection), with size and time limits on the download.
8. **Rate limiting** at the edge and in Django under the `webhook` throttle scope; limits come from the load-test results, not guesses (Environment Configuration §4).
9. **Observability.** Authentication failures, verify-by-pull mismatches and unknown `attempt_id`s are logged at high visibility without the secret, and a sustained rate pages operations (§9, Security Architecture §11).

### 4A.3 Verify-by-pull algorithm
1. Authenticate the header (4A.2-1). Fail → `401`, log, stop.
2. Validate the body against the schema (`attempt_id`, `run_id` required). Fail → `422`, stop.
3. Insert the receipt (4A.2-5). Existing → `200`, stop.
4. Enqueue the processing task and return `200` (the receipt row is already durable).
5. In the task: fetch the run from Dograh with the API key (`workflow_run_id = run_id`).
6. Check that the run exists, is in a terminal state, and that its `initial_context.attempt_id` equals the claimed `attempt_id`. Any mismatch → mark the receipt `rejected`, raise a security alert, do not change state.
7. Derive the event (4A.4) from the **pulled** data, apply the state transition under a row lock, copy artifacts (Dograh Integration §6), enqueue post-call analysis.

### 4A.4 Mapping Dograh results to the event model
| Event (§1) | Derived when |
|---|---|
| `connection.status` (`connected=false`) | Run ended with a never-connected outcome: `busy`, `no-answer`, `failed`, `error` (Dograh Integration §5.2) |
| `connection.status` (`connected=true`) | Run reached `in-progress` / `answered` |
| `call.ended` | Run completed normally with a completed-conversation disposition |
| `call.disconnected` | Run ended after connection with an abnormal `call_status` (network, provider or AI error, customer hang-up before completion) |
| `call.reconnect.result` | Result of the **new** Dograh run created by the Reconnect Manager |

`event_id` is synthesised as `dograh:{run_id}:run_completed` so the idempotency rule of §5 applies unchanged.

### 4A.5 Loss protection
Webhook delivery can fail even with `retry_config`. The reconciler (Dograh Integration §5.4) pulls any attempt stuck in `DIALING`/`IN_CALL` past its ceiling and runs it through the same task as step 5 above. A missed webhook therefore delays an outcome; it never loses one.

---

## 5. Idempotency

- The same logical event may be delivered more than once (provider retries, network duplication). Handlers must be idempotent: processing the same `event_id` twice must not, for example, save two disconnect snapshots or evaluate the retry policy twice.
- Idempotency is enforced by recording processed `event_id` values for a rolling window (at least as long as the provider's own retry window) and short-circuiting duplicates with a `200` response without reprocessing.
- Idempotency must be checked **before** any state-changing action (e.g. before the State Saver writes a snapshot), not after, so a duplicate delivery can never produce two snapshots for one disconnect.

---

## 6. Ordering and race conditions

- Webhook delivery order is not guaranteed to match `occurred_at` order under all network conditions. Handlers should treat `occurred_at` as authoritative for sequencing logic, not arrival order.
- A `call.disconnected` event arriving after a `call.ended` event for the same `attempt_id` (a race between the two) should be treated as a no-op: an attempt already in a terminal state (`EndedNormally`) cannot subsequently be marked `DroppedMidCall`. The handler should log this as an anomaly rather than silently discarding it, since it may indicate a provider-side inconsistency worth investigating.
- Conversely, a `call.ended` arriving after `call.disconnected` has already triggered recovery should also be a no-op against an attempt already past the disconnect decision point.

---

## 7. Response requirements

| Response | Meaning | Provider behavior |
|---|---|---|
| `200` | Event accepted and will be processed (or was already processed — idempotent duplicate) | No retry |
| `401` | Signature verification failed | Provider should not retry — this indicates a configuration problem, not a transient failure |
| `422` | Payload failed schema validation (e.g. missing required `failure_reason`) | Provider should not retry — payload will not become valid on retry |
| `5xx` | Internal error while processing | Provider should retry per its own backoff schedule |

Handlers must return `200` only once the event has been durably queued for processing (or fully processed), not merely received — an early `200` followed by a crash before persisting would silently drop the event, undermining the "no lost conversations" guarantee at the ingestion boundary.

---

## 8. Timeout and retry expectations (provider-side)

- The endpoint must respond within a bounded time (recommended: under 2 seconds) since `call.disconnected` is on the critical path to triggering recovery (Infrastructure Architecture §5, "high latency sensitivity").
- If processing (e.g. the State Saver write) cannot complete within that window, the handler should durably enqueue the raw event and return `200` immediately, processing asynchronously — the acknowledgment to the provider and the completion of the internal save are not required to be the same step, but the enqueue itself must be durable before responding `200`.

---

## 9. Failure modes specific to `call.disconnected`

This event is the most critical in the system, since it's the trigger for the entire recovery flow. Specific handling requirements:

- If signature verification fails for a `call.disconnected` event, it must still be logged at high visibility (not silently dropped) — a forged or misconfigured disconnect event is a security concern, but a legitimate disconnect that fails verification due to a secret rotation issue is an operational emergency, since it would otherwise silently break recovery.
- If the payload is missing `attempt_id` or references an `attempt_id` not currently in an active state, the handler should return `422` and alert operations rather than guessing which attempt it might relate to.

---

## 10. Traceability

| Webhook element | Reference |
|---|---|
| Event types and their triggers | FRS FR-1.6–FR-1.7, FR-2.8, FR-4.1–FR-4.5 |
| Payload enums | Call State Machine §2.1, §3.1 |
| Durable-before-acknowledge requirement | Memory Specification §5, Infrastructure Architecture §4 |
| Security scheme | API Specification `components.securitySchemes.dograhWebhookSecret` (Dograh) and `webhookSignature` (generic) |
| Dograh trust model | §4A, Dograh Integration §4.2, Django Backend Design §5 |

---

*No lost conversations. More opportunities. Higher conversion.*
