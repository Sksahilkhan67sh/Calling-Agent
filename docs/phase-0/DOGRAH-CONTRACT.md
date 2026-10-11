# Dograh contract — what the documentation says (not yet observed live)

All entries below come from docs.dograh.com, read on **2026-10-11** (`llms.txt` index, then the `.md` form of each page).
Nothing here was observed on a running Dograh instance: live behaviour is listed as **UNVERIFIED** and is covered by the
`PENDING_LIVE` items in `VERIFICATION-REPORT.md`. Base URLs in the docs: hosted `https://app.dograh.com`, local `http://localhost:8000`.

## 1. Sources read (URL, all on 2026-10-11)

| Page | URL path |
|---|---|
| Trigger by Agent UUID | /api-reference/runs/trigger-workflow |
| Get run | /api-reference/runs/get-run |
| List runs with usage (org) | /api-reference/runs/list-runs |
| List runs (per workflow) | /api-reference/agents/runs/list |
| Download recordings/transcripts | /api-reference/runs/download |
| Errors | /api-reference/errors |
| API keys overview | /api-reference/api-keys |
| Agents API overview, Update agent | /api-reference/agents, /api-reference/agents/update |
| Webhook node, Webhook payloads | /voice-agent/webhook, /developer/webhooks |
| Workflow definition schema | /developer/workflow-schema |
| Call dispositions | /developer/call-dispositions |
| Calls and runs, Context and variables | /core-concepts/calls-and-runs, /core-concepts/context-and-variables |
| Telephony overview, Telephony webhooks | /integrations/telephony/overview, /integrations/telephony/webhooks |
| Call events | /configurations/call-events |
| Agent UUID | /configurations/agent-uuid |
| Environment variables | /developer/environment-variables |

Not read in this pass (marked where it matters): per-carrier pages, create-from-definition, validate, create-test-run, API-key create/archive pages, scaling, authentication, campaigns, MCP pages.

## 2. Endpoints our design uses

| Purpose | Method and path | Auth | Notes |
|---|---|---|---|
| Start call | `POST /api/v1/public/agent/workflow/{workflow_uuid}` | `X-API-Key` (required) | 200, 404, 422 documented |
| Get run | `GET /api/v1/workflow/{workflow_id}/runs/{run_id}` | `X-API-Key` or `authorization` | **needs the integer `workflow_id`** |
| List runs (workflow) | `GET /api/v1/workflow/{workflow_id}/runs` | same | `page`, `limit` (max 100, default 50), `filters` (JSON string), `sort_by`, `sort_order` |
| List runs (organization) | `GET /api/v1/organizations/usage/runs` | same | `start_date`, `end_date` (ISO 8601 UTC, on `created_at`), `page`, `limit` (max 100), `filters`, `sort_by` (`duration`), `sort_order` |
| Download artifact | `GET /api/v1/public/download/workflow/{token}/{artifact_type}` | none; `token` is the run's `public_access_token` | `artifact_type`: recording, transcript, user_recording, bot_recording; answers **302 redirect to a signed storage URL**; `inline` query flag |
| Agents | `POST /workflow/create/definition`, `GET /workflow/fetch`, `GET /workflow/fetch/{id}`, `PUT /workflow/{id}`, `PUT /workflow/{id}/status` (archive), `POST /workflow/{id}/validate`, `POST /workflow/{id}/runs` (test run) | key or JWT | **no publish endpoint is listed** |
| API keys | `POST/GET /user/api-keys`, `DELETE /user/api-keys/{id}` (archive), `PUT /user/api-keys/{id}/reactivate` | not stated (likely user JWT) | keys are organization-scoped; `last_used_at` exists |
| Stable test trigger | `POST /api/v1/public/agent/test/workflow/{workflow_uuid}` | not stated | named in the Agent UUID page, no description; check before the first live test |

### 2.1 Start call: request body (`TriggerCallRequest`)
`phone_number` (string, required) · `initial_context` (object or null) · `telephony_configuration_id` (integer or null) · `from_phone_number_id` (integer or null, must belong to the resolved configuration) · `model_overrides` (object or null, `additionalProperties: false`).

`model_overrides` keys: `model_configuration_uuid` (uuid), `mode` (`pipeline` | `realtime`), `llm`, `stt`, `tts`, `realtime`, `embeddings` (each `{settings, provider_connection_uuid}`), `llm_fallback` (`version: 1`, up to 2 rules; condition `no_output` with `after_ms` 100–10000, or `error`; target = `{settings, provider_connection_uuid}`).

Response 200 (`TriggerCallResponse`): `status` (string), `workflow_run_id` (**integer**), `workflow_run_name` (string). The response does **not** contain the integer `workflow_id`.

### 2.2 Run object (`WorkflowRunResponseSchema`, get-run and per-workflow list)
Required: `id` (int), `workflow_id` (int), `name`, `mode`, `created_at`, `is_completed` (bool), `transcript_url`, `recording_url`, `cost_info` (object), `definition_id`, `call_type` (`inbound`|`outbound`).
Optional: `workflow_name`, `version_number`, `user_recording_url`, `bot_recording_url`, `transcript_public_url`, `recording_public_url`, `user_recording_public_url`, `bot_recording_public_url`, `public_access_token`, `usage_info`, `initial_context`, `gathered_context`, `logs`, `annotations`.
There is **no top-level `status` field** in the schema, although the Calls and Runs page says a run has a `status` ("Final run state"). Terminal state must be derived from `is_completed` and `gathered_context.call_status` until observed live.

Organization usage list rows (`WorkflowRunUsageResponse`) add `call_duration_seconds`, `dograh_token_usage`, `phone_number` (deprecated), `caller_number`, `called_number`, `disposition`, `charge_usd`, `mode`, `call_type`, plus `initial_context`/`gathered_context`.

### 2.3 List filters (organization endpoint only)
`runId`, `workflowId`, `campaignId` (number) · `callerNumber`, `calledNumber` (text, substring on `initial_context.caller_number` / `.called_number`) · `dispositionCode` (any of `gathered_context.mapped_call_disposition`) · `duration` (min/max seconds) · `callDirection` · `callChannel`. Unknown attributes are **silently ignored** (so an unsupported filter returns unfiltered results, not an error). The per-workflow endpoint documents `filters` only by one example (`dateRange`). **There is no documented filter on an arbitrary `initial_context` key such as `attempt_id`.**

## 3. Webhook node
Executed asynchronously after the run completes; default `POST`; JSON body rendered from `payload_template`.
Node fields: `enabled`, `http_method` (GET|POST|PUT|PATCH|DELETE), `endpoint_url`, `credential_uuid`, `custom_headers` (`[{key,value}]`), `payload_template`. **`retry_config` is named on the Webhook Payloads page but is not a field in the workflow-definition schema.**
Credential types: `NONE`, `API_KEY` (custom header), `BEARER_TOKEN`, `BASIC_AUTH`, `CUSTOM_HEADER`. No HMAC or signed timestamp is documented. The Agents API list has no credential endpoints, so a credential is presumably created in the UI and referenced by `credential_uuid`.
Receiver contract: `2xx` within 30 seconds; non-200 is logged, not retried unless configured; duplicates possible.

Template variables: `workflow_run_id` (int), `workflow_run_name`, `workflow_id` (int), `workflow_name`, `campaign_id` (int|null, Dograh's own campaign; null for us), `call_time` (ISO-8601 UTC, run creation time), `initial_context`, `gathered_context`, `gathered_context.call_status` ("observed reason the call ended", example `user_hangup`), `gathered_context.call_disposition` (raw outcome; falls back to the termination reason when business-outcome extraction is off, which is the default), `gathered_context.mapped_call_disposition`, `cost_info`, `cost_info.call_duration_seconds`, `annotations`, `recording_url`, `transcript_url`. A top-level `call_disposition` is added automatically if the template lacks one.

## 4. Status vocabulary
Telephony status callbacks are normalised to: `initiated`, `ringing`, `in-progress`, `answered`, `completed`, `busy`, `no-answer`, `canceled`, `failed`, `error`; unknown provider statuses pass through unchanged. How these values land in the run record or webhook (`call_status` versus a run `status`) is **not documented** and must be observed. Call events (per-call diagnostics) export only to BigQuery, after the call finishes, with no durable replay, so they are not a real-time hook.

## 5. Context rules
`initial_context` values are usable in prompts as `{{name}}` (fallback `{{name | default}}`); `gathered_context` is not available in prompts, only in webhook payloads and the run record. For telephony runs Dograh adds `caller_number` and `called_number` to `initial_context` automatically (outbound: `called_number` is the **customer's number**), so Dograh stores the customer number in the run. No size limit for `initial_context` is documented.

## 6. Agents and versions
Update accepts `name`, `workflow_definition`, `template_context_variables`, `workflow_configurations`; changing the definition creates a new versioned definition. Response fields include `workflow_uuid`, `version_number`, `version_status`, `current_definition_id`. The Agent UUID is stable across versions. `workflow_configurations.max_call_duration`: integer, 1–1200 seconds, default 300. `call_dispositions`: up to 50 codes (code ≤ 64 chars, description ≤ 1000 chars, 4000 combined); extraction is off by default per workflow.
Definition schema: nodes `startCall`, `endCall`, `agentNode`, `globalNode`, `trigger`, `webhook`, `qa`; edges with `data.condition`; exactly one `startCall` or `trigger`; all nodes except `trigger`/`webhook`/`qa` need a non-empty `prompt`. Validation errors come as `{errors:[{kind,id,field,message}]}`.

## 7. Errors
Body `{ "detail": ... }`; 422 gives an array with `loc`/`msg`/`type`. Codes: 400, 401 (also an archived key), 403 (other organization), 404, 409, 422, 500, 501. Named telephony errors include `QUOTA_EXCEEDED` and `PHONE_NUMBER_NOT_CONFIGURED`. The docs advise retrying 500 with backoff; for the **start-call trigger that advice must not be followed** because a 500 or timeout may still have placed a call.

## 8. Environment variables relevant to production (self-hosted)
`ENVIRONMENT` (local|production|test) · `DEPLOYMENT_MODE` (oss) · `AUTH_PROVIDER` (local|stack) · `OSS_JWT_SECRET` (required, strong) · `OSS_JWT_EXPIRY_HOURS` (default 720) · `ENABLE_SIGNUP` (default true) · `PUBLIC_BASE_URL` / `BACKEND_API_ENDPOINT` · storage: MinIO default (unsigned public-readable object URLs) or `ENABLE_AWS_S3=true` with `S3_*` (real presigned URLs, private bucket) · `TELEPHONY_WS_TOKEN_SECRET` / `TELEPHONY_WS_TOKEN_ENFORCE` (two-step rollout; the token also signs the Telnyx events URL as `?token=`; appears in logs) · `LOG_LEVEL` (default **DEBUG**) · `SENTRY_DSN` · `ENABLE_TELEMETRY` · `DEFAULT_ORG_CONCURRENCY_LIMIT` (default 10, documented under "Campaigns").

## 9. Telephony
Dograh sells no numbers or minutes; the carrier account is always the customer's. Providers documented: Twilio, Vonage, Plivo, Telnyx, Cloudonix, Exotel, Vobiz, Asterisk ARI (+ VICIdial via ARI, custom provider, Dograh-managed SIP via Cloudonix). Signature verification inside Dograh is documented for Twilio (HMAC-SHA1), Plivo and Vobiz (HMAC-SHA256), Vonage (JWT). Telnyx call events are protected only by the `TELEPHONY_WS_TOKEN_SECRET` query token. Audio: Twilio/Plivo/Vobiz 8 kHz μ-law, Vonage 16 kHz PCM, ARI 8 kHz PCM.

## 10. Docs versus design

| ID | Design says | Docs say | Impact |
|---|---|---|---|
| D01 | Pull the run with `workflow_run_id` alone (Webhook Spec §4A.3 step 5) | Get-run needs the integer `workflow_id` too; the trigger response does not return it | Store the integer `workflow_id` per campaign/agent (from get/list agent, or the webhook's `workflow_id`) |
| D02 | Final status is one of busy/no-answer/failed/… (Dograh Integration §5.2) | `call_status` is the observed ending reason (example `user_hangup`); the carrier-status vocabulary is for status callbacks; the run schema has no `status` field | Mapping table must be rebuilt from observed values (V06) |
| D03 | `call_disposition` carries the failure/outcome | It is a business outcome only when extraction is enabled; otherwise it falls back to the termination reason; `mapped_call_disposition` also exists | Decide whether to enable disposition extraction; map from `call_status` first |
| D04 | `retry_config` enables webhook retry (§5.4) | Named on one page, absent from the node schema | Retry may be unavailable; reconciler becomes the primary recovery path |
| D05 | Webhook node is "at the end of the workflow" and fires when the run ends | Fires "when reached" / after a run completes; behaviour for never-connected or mid-call-dropped runs is not stated | If it does not fire, the reconciler is the only path for those outcomes (V03, V06, V07) |
| D06 | Generate workflow, then "publish" via API (§4.3) | No publish endpoint; update creates a new version; `version_status` exists | Live check how a version becomes the published one (V11) |
| D07 | Webhook credential generated with the workflow | No credential endpoints in the Agents API | Credential is created once in the UI; sync only references `credential_uuid` |
| D08 | `DEFAULT_ORG_CONCURRENCY_LIMIT` limits our dialing (§7) | Documented under Campaigns only | Assume Dograh may not enforce it for API triggers; Django enforces its own ceiling (V12) |
| D09 | Download only from an allowlisted host, no redirects to other hosts | The download endpoint answers a 302 to a signed storage URL | Allowlist both the Dograh API host and the storage host; permit at most one redirect, re-validated (implemented in `artifact_download.py`) |
| D10 | `contact_ref` is opaque, number decrypted only at call time (§4.1) | Dograh adds `caller_number`/`called_number` to `initial_context` and stores them; usage rows expose the number | Customer numbers live in Dograh's database; retention and deletion policy needed (Data Privacy) |
| D11 | Reconciler ceiling = "call timeout + margin" | `max_call_duration` is configurable, max 1200 s, default 300 s | Ceiling = configured `max_call_duration` + ring/dial allowance + margin (V07, WEBHOOK-TRUST-MODEL) |
| D12 | Run listing may filter by an `initial_context` value (§4.1) | Only the filters in §2.3; unknown filters are silently ignored | Use the fallback: list by workflow and time window, match `initial_context.attempt_id` client-side (V05) |
| D13 | Errors: trigger never auto-retried | Docs advise retrying 500 | Keep our rule; document why (V08) |
| D14 | Carriers other than Twilio/Plivo/Vobiz/Vonage `[verify]` | Telnyx: token query on the events URL only; Exotel, Cloudonix, Asterisk: no signature verification documented | Carrier shortlist (P0-18) |
| D15 | Self-hosted logging not discussed | `LOG_LEVEL` defaults to DEBUG; media-socket tokens appear in logs | Set `LOG_LEVEL=INFO` or higher and restrict log access (V14) |
| D16 | API-key rotation by archive/replace | Key endpoints under `/user/api-keys`; their auth scheme is not stated | Confirm that rotation can be scripted with a key or needs a user JWT (V13) |
| D17 | Webhook payload template names `campaign_id` via `initial_context` | A top-level `campaign_id` variable exists (Dograh's campaign, null for us) | Keep our own key explicit as `initial_context.campaign_id`; never read Dograh's |
