# Status mapping — version 0.1-docs-only (PROVISIONAL, nothing observed live)

Confidence values: **docs** = stated in documentation, **rule** = our design rule, **hypothesis** = plausible but unobserved. No row below is `observed`. Live runs (V06/V07) must upgrade or replace rows; the mapping stays code-owned and versioned.

## 1. What the documentation gives us
- Carrier status vocabulary (status callbacks): `initiated, ringing, in-progress, answered, completed, busy, no-answer, canceled, failed, error`; unknown values pass through.
- Run fields: `is_completed`; `gathered_context.call_status` (observed reason the call ended, example `user_hangup`); `gathered_context.call_disposition` (raw; equals the termination reason unless business-outcome extraction is on); `gathered_context.mapped_call_disposition`; `cost_info.call_duration_seconds`; transcript and recording URLs.
- Not documented: how the carrier vocabulary appears in the run; a connected/never-connected flag; termination reasons beyond the example; the `invalid_number` signal.

## 2. Mapping table

| Dograh status | disposition | extra run-detail fields | Our reason | Confidence | Evidence |
|---|---|---|---|---|---|
| `busy` | same or termination reason | none | never-connected `busy` | docs (vocabulary only) | /integrations/telephony/webhooks |
| `no-answer` | same | none | never-connected `no_answer` | docs (vocabulary only) | same |
| `failed` | same | carrier reason if exposed (unknown) | `provider_error` by default; `network_error` only if a field names a network cause | rule | Dograh-Integration §5.2 |
| `error` | same | same | `provider_error` (+ alert) | rule | same |
| `canceled` | same | carrier reason | `rejected` only if the carrier reason says declined; otherwise `provider_error`, flagged for review | rule | Dograh-Integration §5.2 |
| (invalid-number outcome) | unknown | carrier-specific | `invalid_number` only after a per-carrier signal is observed; until then `provider_error` | hypothesis | none |
| `completed` + `call_status=user_hangup` | `user_hangup` or business code | duration > 0 | normal end if the conversation reached its end node; otherwise mid-call `customer_hangup` | hypothesis | /developer/call-dispositions (example value) |
| `completed` with agent end-call | business or end-call code | duration > 0 | normal end | hypothesis | same |
| ended after connect, any other `call_status` | unknown | duration > 0 | mid-call `unknown` (retryable by default, conservative) | rule | Call-State-Machine §5.2 |
| any value not in this table | any | any | never-connected: `provider_error` + alert; mid-call: `unknown` + alert | rule | Dograh-Integration §5.2 |

### Trigger-time responses (no run exists)
| HTTP result | Meaning | Action |
|---|---|---|
| 200 | run created | store `workflow_run_id` |
| 4xx (404, 422, 401, 403) | request rejected, no run expected (to confirm V08) | no automatic redial; mark dispatch failed; alert (config or data error) |
| 5xx, timeout, connection error, crash | unknown outcome | `DIAL_REQUESTED` stays; reconcile by window scan (V05); never redial |
| named errors `QUOTA_EXCEEDED`, `PHONE_NUMBER_NOT_CONFIGURED` | carrier/account configuration | pause campaign, page operations |

## 3. Rules
1. **Connected or not.** Until a field is observed, treat a run as connected only if `cost_info.call_duration_seconds` > 0 **and** the transcript contains user speech. Otherwise never-connected.
2. **Refining `failed`/`error`.** Default `provider_error`. Both reasons are retryable by default, so a wrong guess changes analytics and alerting, not behaviour.
3. **`canceled`.** We never cancel calls ourselves. Treat as `provider_error` + review unless the carrier reason says rejected.
4. **`invalid_number`.** Not mapped from any status until a per-carrier signal is observed; the carrier question 6 (CARRIER-SHORTLIST) supplies it. Wrongly retrying an invalid number costs money; wrongly closing a valid one loses a contact, so when the signal is ambiguous prefer `provider_error` and review.
5. **Unknown values** default to `provider_error` (never-connected) or `unknown` (mid-call) and raise an alert; never dropped.
6. The webhook body is not evidence: mapping is applied to the **pulled** run only.

## 4. Code-owned mapping skeleton for Phase 5 (documentation, not product code)
```python
STATUS_MAPPING_VERSION = "0.1-docs-only"

NEVER_CONNECTED = {          # keyed on the observed ending value
    "busy": "busy",
    "no-answer": "no_answer",
    "failed": "provider_error",
    "error": "provider_error",
    "canceled": "provider_error",   # review flag; "rejected" only with carrier reason
}
MID_CALL = {
    "user_hangup": "customer_hangup",   # hypothesis until observed
}
DEFAULT_NEVER_CONNECTED = "provider_error"   # + alert
DEFAULT_MID_CALL = "unknown"                 # + alert
```
Tests to add: extend `TC-DG.11` with one case per row; `TC-DG.16` "every observed value has a row"; a test that the mapping version is written onto the attempt.

## 5. Live observations still needed (V06/V07)
Answered-completed, answered-hang-up, declined, unanswered, phone off, agent-ended; for each record `call_status`, `call_disposition`, `mapped_call_disposition`, duration, `is_completed`, and whether the webhook fired. Vendor questions: CARRIER-SHORTLIST questions 6 and Dograh's mapping of carrier statuses to `call_status`.
