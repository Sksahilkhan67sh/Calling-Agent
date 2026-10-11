# Webhook trust model — decision (provisional until V01–V04 are run live)

## 1. Decision
**Keep the model in Webhook-Specification §4A unchanged:** shared-secret header + TLS + network restriction + verify-by-pull + idempotency receipt + reconciler. Basis: the docs list only static credential types and no signature or signed timestamp (V01, docs-only). If the live capture shows a signing header, add its verification as an extra control; do not remove verify-by-pull.

## 2. Header and secret
- Credential type `API_KEY` (or `CUSTOM_HEADER`) with header `X-Dograh-Webhook-Secret`; exact format to be recorded from the V01 capture.
- Secret ≥ 32 random bytes, unique per environment, in the secrets manager; compared with `hmac.compare_digest`.
- Rotation (current + previous): (1) generate new secret; (2) set `DOGRAH_WEBHOOK_SECRET_PREVIOUS` = old, `DOGRAH_WEBHOOK_SECRET` = new in Django and deploy; (3) update the Dograh credential value; (4) after the longest delivery window (see §4) remove the previous; (5) alert if the previous secret is still being used after that window. The credential must be created in the Dograh UI (no credential API documented).
- Never log the header; redact in access logs (`redact.py` rules).

## 3. Verify-by-pull (what to fetch, what to compare)
1. Authenticate header → 401 on failure. 2. Validate body: `attempt_id` and `run_id` required; types tolerated as string or number (V02) → 422 otherwise. 3. Insert `webhook_receipt(provider='dograh', run_id, event_type='run_completed')`; duplicate → 200. 4. Enqueue and return 200.
5. Task: look up our attempt by `attempt_id`; take the **integer `workflow_id` from our stored agent record** (never from the body); `GET /api/v1/workflow/{workflow_id}/runs/{run_id}`.
6. Compare: run exists (404 → mismatch); `initial_context.attempt_id == attempt_id`; `id == run_id`; `is_completed` true. Mismatch → receipt `rejected`, security alert, no state change.
7. Not complete yet → retry with backoff **2 s, 10 s, 30 s, 90 s** (provisional, ≈ 2 minutes), then leave the attempt to the reconciler. Numbers to be replaced by the V04 lag measurement.
8. Derive the event from pulled data (STATUS-MAPPING), transition under row lock, copy artifacts from pulled URLs only (host allowlist, one re-validated redirect, size/time limits).

## 4. Response-code policy (replaces the unverified assumptions in §7)
| Case | Code | Why |
|---|---|---|
| Valid and queued, or duplicate | 200 | receipt row durable first |
| Bad or missing secret | 401 | configuration problem |
| Schema failure | 422 | will not become valid |
| Our transient failure (database/broker) | 503 | transient |
Dograh retry behaviour on non-2xx is unknown (V03), so correctness must not depend on it. Respond within 2 s; Dograh waits up to 30 s per the docs. Receipt retention ≥ the longest possible redelivery window; until V03 is measured keep 7 days.

## 5. Network restriction
Accept only from the self-hosted Dograh egress/private address (security group or mTLS at the proxy); own path `/webhooks/dograh/run-completed`; separate rate limit from the load test (Environment-Config §4). Source address of requests to be recorded in V01.

## 6. Idempotency and replay
Receipt key `(provider, run_id, event_type)`; replay of a body cannot change a terminal attempt and cannot assert anything the pulled run does not confirm.

## 7. Reconciler thresholds (provisional)
Ceiling for `DIALING`/`IN_CALL` = `max_call_duration` (Dograh workflow setting, 1–1200 s, default 300 s) + **120 s** dial/ring allowance (carrier ring timeout unknown) + **60 s** webhook/verify margin. Default 300 s → **480 s**; worst case 1200 s → **1380 s**. Run every 60 s. If the webhook turns out not to fire for abnormal or never-connected ends (V03/V06/V07), the reconciler becomes the primary path for those outcomes and the ceiling for never-connected attempts should be shortened to dial allowance + margin (≈ 3 minutes).
Reconcile uses the verify-by-pull task; for attempts without `provider_run_id`, use the window scan (V05).

## 8. Open items
V01–V04 live checks (OPEN-QUESTIONS Q1–Q4). Decision may only change if a signing or timestamp header exists or if retries turn out to be configurable.
