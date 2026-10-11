# Changelog — V2 → V3 (Dograh voice runtime + Django backend + authenticated everywhere)

## What changed

| Requirement | Result |
|---|---|
| LLM, TTS, STT, webhook provider = **Dograh** | New `Architecture/Dograh-Integration.md`; provider boxes in System/Infrastructure Architecture now map to Dograh; Environment-Config has `DOGRAH_*` variables and the Dograh stack's required production settings (§2.9) |
| Framework = **Django** | New `Backend/Django-Backend-Design.md` (DRF, Celery, project layout, auth, dialer, webhook view). The Word approach doc no longer says NestJS/BullMQ/LiveKit/Deepgram/OpenAI/ElevenLabs |
| Everything **secure and authenticated** | `Security-Compliance/Security-Architecture.md` §2 is now a 13-surface authentication table; Webhook-Specification §4A defines the Dograh webhook trust model; API spec requires auth on every endpoint (only login/refresh are open) |

## Files

New: `Architecture/Dograh-Integration.md`, `Backend/Django-Backend-Design.md`, `CHANGELOG-V3.md`

Updated: `AI_Calling_Agent_Scalable_Production_Approach.docx`, `Architecture/System-Architecture.md`, `Architecture/Infrastructure-Architecture.md`, `Backend/Webhook-Specification.md`, `Backend/API-Specification.yaml` (validated as OpenAPI 3.0), `Backend/Database-Design.md`, `Security-Compliance/Security-Architecture.md`, `Security-Compliance/Threat-Model.md`, `Deployment/Environment-Config.md`, `Deployment/Deployment-Guide.md`, `Deployment/Monitoring.md`, `Deployment/Incident-Runbook.md`, `Deployment/Rollback-Runbook.md`, `Testing/Test-Cases.xlsx` (92 → 113 cases), `Testing/Test-Plan.md`, `Testing/Load-Test-Plan.md`, `Testing/QA-Report.md`

Not changed: PRD / FRS / User Stories (.docx), Acceptance-Criteria, AI specs, Recording-Consent, Data-Privacy, Cost-Model / Capacity-Planning (.xlsx), Project-Milestones. None of them name a specific provider or framework, but the cost and capacity models should be re-priced once the real STT/LLM/TTS/carrier choices are made in Dograh.

## Design decisions to review

1. **Dograh Campaigns are not used.** Django owns campaigns, suppression and retries so there is one source of truth for compliance. Dograh only receives "start this call".
2. **Dograh webhooks carry no HMAC signature** (only a static credential header). The old `X-Provider-Signature` + 5-minute freshness rule could not be kept. Replacement: shared secret + network restriction + **verify-by-pull** + idempotency receipt + reconciler.
3. **Mid-call disconnects are learned when the run ends**, not live. Reconnect = a new Dograh run seeded with saved context.
4. **Retry schedule lives in PostgreSQL** (`next_dispatch_at`), dispatched by Celery beat. This replaces the old "no polling loop" preference because long-ETA broker tasks are not reliably durable.
5. **Self-hosted Dograh in the same VPC/region** is the recommended default; Dograh Cloud would put recordings and transcripts at a third party.

## Open items marked [verify] in the docs

- Whether Dograh can sign webhook bodies or send a signed timestamp.
- Whether the Dograh run-listing API can filter by an `initial_context` value (needed for crash recovery after a trigger call).
- Signature verification for carriers other than Twilio, Plivo, Vobiz and Vonage (check before choosing Exotel, Telnyx, Cloudonix or Asterisk).
- Exact mapping of Dograh failure statuses to `invalid_number` / `rejected` per carrier.
- Dograh API keys are organization-scoped only; mitigations are listed in Security Architecture §2.
