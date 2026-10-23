# AI Calling Agent — Django Backend

Build from scratch. Source of truth: `/docs` (V3 docs). Use the /production-engineering skill.
Stack: Django 5 + DRF, PostgreSQL, Celery + Redis, S3. Dograh = telephony/STT/LLM/TTS/webhook provider. Django never touches live audio.

## Loop (run until all phases are DONE; stop only if BLOCKED)
1. Read `PROGRESS.md`. Take the first unfinished phase.
2. Read ONLY the doc sections that phase needs (grep / line ranges). Never cat whole docs. Never re-read a file already read.
3. Implement. Run tests + `manage.py check --deploy` + bandit. Show last 15 lines of output only.
4. Failure: max 3 fix attempts, then mark BLOCKED in PROGRESS.md and continue with what is unblocked.
5. Commit. Update `PROGRESS.md` (max 5 lines: done / open [verify] / blockers). Next phase.

## Code rules
- Least code that fully implements the logic. 5 lines suffice → write 5.
- No wrapper/base class/helper unless used 2+ times. Django/DRF built-ins first.
- No dead code, TODO stubs, fake logic, or mock data in app code.
- Comments: one-line "why" only when non-obvious.
- No unrequested refactors, features, or files outside the current phase.

## Production rules (non-negotiable)
- State changes in `transaction.atomic`; claim work with `select_for_update(skip_locked=True)`.
- Every external call has a timeout. Dograh trigger call is never auto-retried.
- Celery tasks idempotent: `acks_late`, `reject_on_worker_lost`, time limits, separate queues (dial, webhook, recovery, analysis, default).
- Suppression checked at dial time (by `phone_hmac` + contact id), not only at enqueue.
- Phone numbers encrypted; lookups via `phone_hmac`. No secrets, phone numbers, API keys, recording URLs in logs. Config via env only.
- Webhook body is a notification, not evidence: verify-by-pull from Dograh, receipt written before ack.
- Migrations backward-safe (no destructive change in one step).
- Test failure paths for every critical flow: duplicate webhook, crash mid-dial, lost webhook, suppression added mid-wait.
- Docs marked `[verify]`: never assume. Use the safest fallback and log it in PROGRESS.md.
- Never say "done" unless tests ran and passed.

## Token rules
- No explanations, recaps, or echoing code back. One line per step, then tool calls.
- Targeted edits over rewrites. grep/head/tail/line ranges over full reads. Batch independent commands.

## Key docs (read per phase, sections only)
- Backend/Django-Backend-Design.md (§9 order), Database-Design.md, API-Specification.yaml, Webhook-Specification.md (§4A)
- Architecture/Dograh-Integration.md, Call-State-Machine.md
- Security-Compliance/Security-Architecture.md, Deployment/Environment-Config.md
