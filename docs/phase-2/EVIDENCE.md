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
