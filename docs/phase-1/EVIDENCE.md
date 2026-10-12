# Phase 1 evidence

All commands were run in this environment (Python 3.12.3, PostgreSQL 16.15 and Redis 7 installed locally, no Docker).
Clean-clone runs used `git clone --branch phase-1/foundation` into a fresh directory and `pip install --require-hashes`.

## P1-00 Recon
`git status` clean; `main` contains `docs/phase-0/`; branch `phase-1/foundation` created. Versions recorded in DECISIONS.md D-01
with PyPI dates (re-verified: Django 5.2.18 released 2026-10-06 and cryptography 50.0.2 on 2026-09-30 were younger than 14 days, so not used).

## P1-01 Hygiene
`pre-commit run --all-files` (with `SKIP=gitleaks`): all hooks Passed. The `gitleaks` hook could not install (`URLError: Name or service
not known` while fetching its toolchain). Instead: `gitleaks git` over the whole branch history: `24 commits scanned ... no leaks found`.
One real finding on the way: `detect-private-key` flagged fake PEM markers in tests; fixed by assembling the marker at runtime.
`make lint|typecheck|test|security|check-deploy|contract` all succeed from a clean clone.

## P1-02 Dependencies
`pip install --require-hashes -r requirements/dev.txt` and `prod.txt` in a clean venv: rc=0.
`pip-audit -r requirements/prod.txt -r requirements/dev.txt --require-hashes`: `No known vulnerabilities found`.
Script check of all 102 pins against PyPI: none younger than 14 days.

## P1-03 Settings
`check --deploy --fail-level WARNING` with generated throwaway env: prod rc=0 and staging rc=0, `System check identified no issues (0 silenced).`
(An earlier run showed two drf-spectacular warnings for the health views; fixed with `extend_schema(exclude=True)`.)
`tests/config/test_settings.py`: posture for prod and staging, DEBUG never on, all 12 required variables removed in turn (message names the
variable and contains no value), placeholder/short/identical keys, bad host, missing `sslmode`, bad DB URL.

## P1-04 Containers (PARTIAL)
Verified: `docker/compose.dev.yml` and workflows parse as YAML; `actionlint` OK. Run directly (no container): Gunicorn + `uvicorn_worker.UvicornWorker`
with `config.settings.prod` and a throwaway env: `GET /healthz` 200 with `X-Request-ID`; `GET /readyz` 503 `{"checks":{"database":false,"redis":false,"broker":false}}`
with no details; plain-HTTP non-probe path 301; wrong Host 400; access log shows `GET /healthz?token=[REDACTED]&x=1` and the raw token never appears.
**Not verified:** image build, non-root `id -u`, compose health, `migrate` in compose, `hadolint` (not installed).

## P1-05 Celery
Unit: `heartbeat.apply` eager with context. Integration (`tests/test_celery_integration.py`, real Redis, real `celery worker --pool=solo` and
`celery beat` subprocesses): beat log `Sending due task core-heartbeat`; worker log line `{"logger": "apps.core.tasks", "message": "heartbeat", "task_id": "..."}`;
a task sent with `log_context={"request_id": X}` shows `request_id` X in the worker's JSON log (context crosses the broker).

## P1-06/08/09/10/11/12/13
Full suite from the clean clone: `181 passed`, coverage `TOTAL 651 stmts, 0 missed, 100 %` on `apps/core` and `config` (gate is 90 %).
Highlights: crypto rotation, tamper, AAD mismatch, 5000-nonce uniqueness, independently computed HMAC vector (openssl); redaction table-driven positive and
negative cases, 9 hostile inputs under 2 s each, log-capture test (secrets, recording URL, signed URL, phone never appear); middleware accepted/rejected ids,
cleanup after exception, async path; default-deny walker with 4 violation types and negative test; throttles 429 with `Retry-After`, scope isolation, real Redis;
health with hung dependency (<1.5 s), unreachable real DB/Redis/broker (503 naming all three), healthy real services (200).

## P1-07 User
`makemigrations --check --dry-run`: `No changes detected`. `migrate` on an empty `agent_test` database: all contrib auth migrations and
`accounts.0001_initial... OK`. Tests: UUID pk, case-insensitive uniqueness including `bulk_create`, Argon2 hash.

## P1-14 Contract
`python scripts/check_api_contract.py`: `contract operations compared: 0`, `not yet implemented (informational): 21`, `RESULT: OK (no drift for implemented paths)`; 8 unit tests with synthetic schemas.

## P1-15 CI (PARTIAL)
`actionlint .github/workflows/ci.yml`: no findings. Locally run: lint, test (unit then full, coverage), migrations, deploy-check, security (bandit: `No issues identified`; pip-audit clean;
gitleaks binary), contract. **Not run:** GitHub-hosted execution, the `docker` job, gitleaks-action itself. Human must confirm green CI on the PR.

## P1-16 Test infrastructure
`pytest -m "not integration"` with PostgreSQL and Redis stopped: `173 passed, 8 deselected`. Fixtures: settings loader, throwaway prod env factory, log capture, Redis client with per-test key prefix, `frozen_time`.

## P1-17 Docs drift
`test_env_variables_doc_matches_settings` fails both for an undocumented variable and for a documented variable never read.

## P1-19 Security self-review
| Check | Answer | Evidence |
|---|---|---|
| No secret defaults in prod paths | Yes | `required()` has no default; only `test.py` sets fake values; tests for each missing variable |
| DEBUG impossible in staging/prod | Yes | literal `False`; `test_prod_ignores_debug_environment_variable` |
| ALLOWED_HOSTS explicit | Yes | wildcard rejected; `evil.test` got 400 in the Gunicorn run |
| CORS explicit, empty by default | Yes | `CORS_ALLOWED_ORIGINS == []`, `ALLOW_ALL` false (tested); dev adds only `http://localhost:3000` |
| Every view default-deny | Yes | `tests/test_default_deny.py` |
| Error handler leaks nothing | Yes | `test_unhandled_error_returns_generic_500_without_internals` |
| Logs redacted | Yes | log-capture test; live Gunicorn access log |
| Argon2 first | Yes | settings test |
| Cookies secure, HSTS | Yes | posture test; `check --deploy` zero warnings |
| Admin site | Not installed, not mounted | `grep contrib.admin` finds nothing |
| Container non-root | Written (`USER app`, uid 10001) | **runtime check not run here** |
| Dev ports on localhost only | Yes | compose lines `127.0.0.1:5432/6379/8000` |
| No `latest` tags | Yes | grep finds none |
| Hashes enforced on install | Yes | Dockerfile, Makefile, CI use `--require-hashes` |
| Dependency audit clean | Yes | pip-audit |
| Compose has no real credentials | Yes | only `${VAR}` references |
| `.env.example` obviously fake | Yes | `change-me-dev-only...`, base64 of "dev-only-NOT-A-SECRET..." |
Residual risks: OQ-03, OQ-06, OQ-07, OQ-11.

## P1-20 / P1-22 Not verified here (exact commands for the human)
```
cp .env.example .env
docker compose --env-file .env -f docker/compose.dev.yml up -d --build
curl -s localhost:8000/readyz                       # expect 200
docker compose --env-file .env -f docker/compose.dev.yml logs worker | grep heartbeat   # within ~90 s
docker compose --env-file .env -f docker/compose.dev.yml run --rm --entrypoint id api -u  # expect non-zero uid
docker compose --env-file .env -f docker/compose.dev.yml down -v
```
plus GitHub Actions on the PR (all seven jobs).
