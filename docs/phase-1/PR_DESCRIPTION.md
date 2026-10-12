Title: Phase 1 — Foundation (Django skeleton, settings, Celery, CI, core security utilities)

## Summary
Builds the skeleton every later phase stands on: project layout, settings split, containers, PostgreSQL, Celery + Redis, CI gates, and the
`core` app (field encryption, blind index, log redaction, request/trace context, health, default-deny permissions, throttle scopes).
It deliberately contains no contacts, campaigns, calls, Dograh client, webhooks or authentication endpoints.

## What changed
- `backend/`: Django 5.2.17 LTS, DRF, settings `base/dev/test/staging/prod` (prod fails fast), hashed lock files, `config/celery.py` (JSON-only, acks late, 5 queues declared, heartbeat only in beat).
- `apps/core`: `settings_utils`, `crypto` (AES-256-GCM, rotating keys, AAD; HMAC blind index), `logging` (JSON, contextvars, redaction filter on every handler), `middleware`, `permissions`, `throttles`, `health`, `tasks`.
- `apps/accounts`: custom `User` skeleton (UUID pk, ci-unique email), migration `0001`.
- `docker/` (multi-stage non-root image, gunicorn + Uvicorn worker, dev compose), `.github/workflows/ci.yml` (7 jobs), Dependabot, pre-commit, Makefile, README section.
- `scripts/check_api_contract.py` (informational; fails only on drift for implemented paths).

## Evidence
| Task | Command | Result | Where |
|---|---|---|---|
| Tests | `make cov` (clean clone) | 181 passed, 100 % on `apps/core` + `config` (gate 90 %) | EVIDENCE P1-06..13 |
| Unit only | `pytest -m "not integration"` with services stopped | 173 passed | P1-16 |
| Deploy check | `check --deploy --fail-level WARNING` (prod, staging) | 0 warnings | P1-03 |
| Types / lint | `mypy .` (strict on core/config), `ruff` | clean | P1-01 |
| Security | `bandit -ll`, `pip-audit`, gitleaks on 24 commits | no issues | P1-02, P1-15 |
| Celery | real worker + beat vs real Redis | heartbeat consumed, context propagated | P1-05 |
| Migration | `migrate` on empty DB | `accounts.0001_initial... OK` | P1-07 |

## Decisions
See `docs/phase-1/DECISIONS.md` (key format, logging approach, broker default, user model choices, queue naming).

## Not verified here
No Docker daemon and no GitHub-hosted CI were available. Please run: the compose commands in `docs/phase-1/EVIDENCE.md` (image build, non-root `id -u`, `/readyz` 200,
heartbeat in worker logs), and confirm all seven CI jobs are green on this PR. The `gitleaks` pre-commit hook could not install offline (the binary was run instead).

## Phase 0 inputs consumed
`DOGRAH_EFFECTIVE_CONCURRENCY` added as a required, validated, unused variable (Phase 0 DP-12: Django enforces its own ceiling in Phase 4). `DOGRAH_WEBHOOK_HEADER_NAME` added for redaction.
Deferred and listed in OPEN-QUESTIONS: verify-by-pull and reconciler timings, Dograh run records holding customer numbers (privacy note for Phase 3/5), live capture items V01–V14.

## Risks and rollback
No production data or deployments are affected. Migrations: `accounts.0001` only. Rollback = revert the merge commit.

## Reviewer checklist
1. Follow README to a green `make test` and a healthy compose stack.
2. Confirm CI is green on this PR (all seven jobs).
3. Spot-check three modules in `core` and their tests (suggest `crypto`, `logging`, `test_default_deny`).
4. Read DECISIONS.md and OPEN-QUESTIONS.md (OQ-01 rate limits need real values before staging).
5. Confirm no secrets in the diff (run gitleaks locally).
