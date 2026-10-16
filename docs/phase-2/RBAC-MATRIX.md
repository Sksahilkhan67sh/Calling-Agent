# Phase 2 — RBAC matrix

Generated from `backend/apps/accounts/roles.py` by `python -m scripts.gen_rbac_matrix`.
Do not edit by hand: a test fails when this file drifts from the code.
`own` = rows in the caller's scope via `for_user()`; `all` = every row.

| Capability | Campaign Manager | Admin | Sales / Follow-up | System | API client grantable | Description |
|---|---|---|---|---|---|---|
| `campaigns.create` | yes | yes | - | - | - | Create campaigns |
| `campaigns.view_own` | yes | yes | - | - | - | View campaigns in the caller's scope |
| `campaigns.view_all` | - | yes | - | - | yes | View every campaign |
| `campaigns.update_status` | yes | yes | - | - | - | Pause, resume or complete campaigns in scope |
| `contacts.import` | yes | yes | - | - | - | Import contacts into campaigns |
| `contacts.view_own` | yes | yes | yes | - | - | View contacts in the caller's scope |
| `contacts.view_all` | - | yes | - | - | yes | View every contact |
| `contacts.suppress` | yes | yes | - | - | - | Record a do-not-call request for contacts in scope |
| `attempts.view_own` | yes | yes | - | - | - | View call attempts in the caller's scope |
| `attempts.view_all` | - | yes | - | - | yes | View every call attempt |
| `analytics.view_own` | yes | yes | - | - | - | View analytics of campaigns in scope |
| `analytics.view_all` | - | yes | - | - | yes | View cross-campaign analytics |
| `retry_policy.view` | yes | yes | - | - | - | Read a campaign's retry policy |
| `retry_policy.write` | - | yes | - | - | - | Configure a campaign's retry policy |
| `agent_config.view` | yes | yes | - | - | - | Read a campaign's agent configuration |
| `agent_config.write` | - | yes | - | - | - | Configure a campaign's agent |
| `suppression.manage` | - | yes | - | - | - | View and manage the suppression list |
| `final_output.view` | yes | yes | yes | - | yes | Read Final Output records in scope |
| `recordings.listen` | - | - | - | - | - | Listen to call recordings (granted per user, audited) |
| `transcripts.view` | - | - | - | - | - | Read call transcripts (granted per user, audited) |
| `audit.view` | - | yes | - | - | - | Read audit events |
| `users.manage` | - | - | - | - | - | Manage users (management commands only in Phase 2) |
| `api_clients.manage` | - | - | - | - | - | Manage API clients (management commands only in Phase 2) |

Capabilities held by no role (`recordings.listen`, `transcripts.view`, `users.manage`, `api_clients.manage`) are granted to individual users only, or are management-command level in Phase 2.
`System` has no capabilities and cannot log in: service accounts use database roles and
internal code paths.
