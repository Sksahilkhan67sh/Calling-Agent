# Calling-Agent

Outbound AI calling agent backend (Django + Dograh voice runtime).
Design documents live in `ai_calling agent/`. Work is delivered in phases; see `docs/` per phase.

## Backend (Phase 1: foundation)

Django 5.2 LTS + DRF modular monolith in `backend/`, Celery + Redis, PostgreSQL 16. Phase 1 contains only the skeleton and the
`core` utilities (field encryption, blind index, log redaction, request context, default-deny, throttles, health). No business
models, no Dograh client, no webhook endpoints.

### Prerequisites
Python 3.12, Docker with Compose v2 (for the full stack), GNU Make. Tests also run against any local PostgreSQL 16 + Redis 7.

### First run (5 commands)
```bash
cp .env.example .env            # fake dev-only values; never commit .env
make install                    # venv from hashed lock files
make up                         # postgres, redis, migrate, api, worker, beat (all on 127.0.0.1)
curl -s localhost:8000/readyz   # {"status":"ok","checks":{...}}
make test                       # needs PostgreSQL and Redis on localhost (see below)
```

### Everyday commands
| Task | Command |
|---|---|
| Unit tests only (no services) | `cd backend && pytest -m "not integration"` |
| Full tests (real PostgreSQL, Redis, Celery) | `make test` |
| Coverage gate (90 % on `apps/core`, `config`) | `make cov` |
| Lint / format / types | `make lint` / `make format` / `make typecheck` |
| Production checks | `make check-deploy`, `make security` |
| API contract check | `make contract` |
| Logs / stop | `make logs` / `make down` |

Integration tests expect PostgreSQL at `127.0.0.1:5432` (role `agent`, password `agent-dev-only`, a database named
`agent_test` must exist) and Redis at `127.0.0.1:6379`; defaults are in `backend/config/settings/test.py`.

### Adding a dependency
Add it to `backend/requirements/{base,prod,dev}.in`, run `make lock`, and confirm the new pins are at least 14 days old.
Install is hash-enforced (`pip install --require-hashes`).

### Celery locally
`cd backend && celery -A config worker -Q default --loglevel=INFO` and, in another shell, `celery -A config beat`.
The `heartbeat` task logs one JSON line per minute.

### Migration rules
Every migration must be additive and backward-compatible (Deployment-Guide §5): add nullable columns or tables first, backfill,
then enforce; never rename or drop in the same release as the code change. Migrations are a deploy step and never run from the
container entrypoint.

### Where things live
`docs/phase-1/`: `DECISIONS.md` (why), `ENV-VARIABLES.md` (every variable), `OPEN-QUESTIONS.md`, `DOC-PATCHES.md`,
`PROGRESS.md`, `EVIDENCE.md`, `PHASE-2-HANDOFF.md`. Design documents are in `ai_calling agent/` and are not edited by phases.
