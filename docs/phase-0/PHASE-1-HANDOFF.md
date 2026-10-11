# Phase 1+ handoff (docs-only Phase 0)

Values marked **pending live** must not be hard-coded; they are inputs that Phase 0 could not observe.

| Item | Value | Status |
|---|---|---|
| Dograh deployment | self-hosted, same VPC/region (instruction given for this run) | decided |
| Carrier | none chosen; shortlist and vendor questions in CARRIER-SHORTLIST.md; needs target country, volume, price | open |
| Dograh integer `workflow_id` | must be stored per agent/campaign next to the Agent UUID | decided (from docs) |
| Start-call endpoint | `POST /api/v1/public/agent/workflow/{workflow_uuid}`; response `workflow_run_id` is an integer | docs |
| Effective concurrency | formula `floor(min(carrier channels, server capacity, org limit if enforced) × 0.9)`; baseline peak ≈ 22 connected calls (derived from Capacity-Planning, ring time excluded); carrier channels and server capacity unknown | **pending live / vendor** |
| Webhook header name | `X-Dograh-Webhook-Secret` (design default) | pending V01 |
| Webhook retry config | none assumed; do not depend on retries | pending V03 |
| Receipt retention | 7 days provisional | pending V03 |
| Verify-by-pull backoff | 2/10/30/90 s then reconciler | provisional, pending V04 |
| Reconciler ceiling | `max_call_duration` + 120 s + 60 s (480 s default, 1380 s worst case); run every 60 s | provisional |
| Recording/transcript policy | download server-side immediately from pulled URLs; allowlist API host + storage host; ≤ 1 re-validated redirect; expiry and formats pending live | partly decided |
| List-runs fallback | org endpoint, `start_date`, `workflowId`, client-side match on `initial_context.attempt_id`; `DIAL_REQUESTED` row first | decided |
| `initial_context` size limit | unknown; working limit 8 KB; flat string keys | pending V09 |
| Status mapping version | `0.1-docs-only` | provisional |
| Agent sync | create/update definition; publish mechanism and credential creation unknown; webhook credential created once in the UI | pending V11 |

## Changes to the Phase 1–8 plan
1. **Phase 4 (dialer):** enforce our own concurrency semaphore; do not rely on Dograh's limit. Add a `DIAL_REQUESTED` state and the window-scan reconciler path.
2. **Phase 5 (webhook):** store integer `workflow_id` per agent; accept string/numeric payload values; reconciler may be the primary path for never-connected outcomes if the webhook does not fire.
3. **Phase 6/agent sync:** possible manual publish step and UI-created webhook credential; add a "published version" guard before campaign start.
4. **Privacy:** customer numbers are stored in Dograh run records; retention and deletion must cover Dograh's database and storage.
5. **New risk:** run `V01–V09` live before M3.2 work depends on webhook semantics; a failed assumption (webhook not firing on abnormal ends, no publish API) moves effort into the reconciler and the sync service.
6. Carrier choice gates the cost model, invalid-number mapping and channel limits; start vendor conversations now.
