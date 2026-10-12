# Phase 2 evidence

## P2-00
- `git merge-base --is-ancestor f39a748 main` and `150389e ... main`: both true (Phase 1 and Phase 0 tips are in main).
- `git clone` of the public repo succeeded without credentials.
- `Test-Cases.xlsx` scanned: 23 auth/RBAC/security-related rows (see TEST-TRACEABILITY.md).
- Sandbox probe: Python 3.12.3; psql/postgres/redis-server/docker not found.

## P2-01
- Pins diff vs Phase 1 (base/prod/dev): only `django-axes`, `djangorestframework-simplejwt`, `pyjwt`, `pyotp` added.
- `python -m venv /tmp/cleanvenv && pip install --require-hashes -r backend/requirements/dev.txt`: success.
- `pip-audit -r requirements/prod.txt -r requirements/dev.txt --require-hashes`: "No known vulnerabilities found" (with pyjwt 2.15.0; 2.14.0 was flagged with two advisories).
- `pytest -q -m "not integration"`: 173 passed, 8 deselected. `ruff check .`: all checks passed.
- Hygiene gate: manual secret grep on staged diff clean (`github_pat_`, `ghp_`, `sk-`, `Bearer `, private-key headers, `otpauth://`). `pre-commit run` could NOT run in this sandbox (hook environments need network access that is blocked: `URLError: Name or service not known`). NOT VERIFIED here; reviewer/CI must run `pre-commit run --all-files` (gitleaks included).

## P2-02
- `pytest -q -m "not integration"`: 226 passed (was 173): +53 tests in `tests/config/test_settings_auth.py`, plus the Phase 1 parametrized fail-fast test now covers `LOGIN_RATE_LIMIT_PER_MINUTE`, `AXES_FAILURE_LIMIT`, `TRUSTED_PROXY_COUNT`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` (missing → `ConfigError` naming only the variable, no value leaked).
- `tests/config/test_settings.py::test_env_variables_doc_matches_settings` (env drift): passes with the updated `ENV-VARIABLES.md`.
- `DJANGO_SETTINGS_MODULE=config.settings.{prod,staging} python manage.py check --deploy --fail-level WARNING` with a throwaway env from `scripts/gen_throwaway_env.py`: "System check identified no issues (0 silenced)" for both.
- Negative: unsetting `AXES_FAILURE_LIMIT` makes prod fail at import with `AXES_FAILURE_LIMIT is required but missing or empty`.
- `ruff check`, `ruff format --check`, `mypy apps config`: clean (29 source files).
- Not covered yet: coverage percentage for the new settings code (measured in P2-21).

## Environment (updated after P2-02)
- `apt-get install postgresql redis-server`; `pg_ctlcluster 16 main start`; `redis-server --daemonize yes`. `psql` reports PostgreSQL 16.15; `redis-cli ping` → PONG.
- Dev role/database created to match `config/settings/test.py` (`agent`/`agent_test`, `CREATEDB` so pytest-django can create its test database).
- `pytest -q -m integration`: 8 passed (Phase 1 integration tests against real services).

## P2-03
- `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: "No changes detected".
- `sqlmigrate accounts 0002`: three `ADD COLUMN` statements, no `DROP DEFAULT`, no table rewrite beyond PostgreSQL's metadata-only default; `--backwards` drops the three columns.
- `pytest -q tests/accounts tests/test_accounts.py` (real PostgreSQL 16): all pass, including `test_migration_0002_applies_over_phase1_data_and_reverses` (0001 → row inserted → 0002 → defaults 0/''/NULL; older-code INSERT still works; migrate back to latest) and the empty-database path (test DB creation applies 0001 and 0002).
- Mutation spot-checks (protection removed → named test fails, then restored):
  1. `save()` writes `auth_epoch` again → `test_stale_copy_cannot_roll_the_epoch_back` FAILED.
  2. deactivation no longer bumps → `test_deactivation_bumps_but_reactivation_and_resave_do_not` FAILED.
- Full suite: 260 passed (unit + integration, real PostgreSQL and Redis); coverage `apps/core`, `apps/accounts`, `config`: 100 % (799 statements, 0 missed).
- `ruff check`, `ruff format --check`, `mypy apps config` (strict on accounts): clean.

## P2-04
- `pytest -q` (real PostgreSQL + Redis): 378 passed, coverage 100 % (884 statements). New: `tests/accounts/test_roles_matrix.py` (full role x capability cell test, hand-written truth table, client-grantable invariants, generated-doc drift test) and `tests/accounts/test_sync_roles.py` (first run, second run is a no-op, command idempotent, drift repaired in both directions, System drift removed, per-user grants untouched, missing permission fails closed).
- `python manage.py makemigrations --check --dry-run`: no changes; `sqlmigrate accounts 0003`: no-op (Meta options only).
- Mutation spot-checks (protection removed -> named tests fail, then restored):
  1. Campaign Manager given `retry_policy.write` -> 4 failures (`test_role_capabilities_match_the_reviewed_truth_table[Campaign Manager]`, `test_only_admin_can_write_configuration_or_manage_suppression`, the cell test, and the generated-doc drift test).
  2. `sync_roles` stops removing drift -> `test_drift_is_repaired_in_both_directions` and `test_system_group_drift_is_removed` fail.
- A first attempt at mutation 1 hit the wrong line (registry tuple instead of the role set); it was discarded and redone precisely.
- `ruff`, `ruff format --check`, `mypy apps config scripts`: clean.
- NOT DONE here: the audit event for `rbac.sync` (needs the audit app, P2-06).
