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
