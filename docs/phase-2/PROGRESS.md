# Phase 2 progress

| ID | Task | Status | Evidence | Commit | Notes |
|---|---|---|---|---|---|
| P2-00 | Recon and scaffolding | DONE | EVIDENCE P2-00 | e22ab28 | deps: - |
| P2-01 | Dependencies (simplejwt, axes, pyotp) | DONE | EVIDENCE P2-01 | 241630d | deps: P2-00 |
| P2-02 | Settings and environment | DONE | EVIDENCE P2-02 | c4a65ef | deps: P2-01 |
| P2-03 | User model extension | TODO | - | - | deps: P2-02 |
| P2-04 | Roles, capabilities, RBAC matrix | TODO | - | - | deps: P2-03 |
| P2-05 | Permission classes and object scoping | TODO | - | - | deps: P2-04 |
| P2-06 | audit app (append-only) | TODO | - | - | deps: P2-03 |
| P2-07 | MFA (TOTP) with encrypted seeds | TODO | - | - | deps: P2-03, P2-06 |
| P2-08 | Cookie JWT authentication | TODO | - | - | deps: P2-03, P2-05 |
| P2-09 | Auth endpoints | TODO | - | - | deps: P2-07, P2-08 |
| P2-10 | Lockout, client IP, throttling | TODO | - | - | deps: P2-09 |
| P2-11 | Session revocation semantics | TODO | - | - | deps: P2-09 |
| P2-12 | Machine clients (api_client) | TODO | - | - | deps: P2-05, P2-06 |
| P2-13 | Management commands | TODO | - | - | deps: P2-04, P2-06, P2-07, P2-12 |
| P2-14 | OpenAPI and contract check | TODO | - | - | deps: P2-09 |
| P2-15 | Attack-oriented security test suite | TODO | - | - | deps: P2-09..P2-12 |
| P2-16 | Logging and redaction verification | TODO | - | - | deps: P2-09, P2-12 |
| P2-17 | Database roles and privileges | TODO | - | - | deps: P2-06 |
| P2-18 | CI updates | TODO | - | - | deps: P2-15, P2-17 |
| P2-19 | Documentation | TODO | - | - | deps: P2-15 |
| P2-20 | Security self-review | TODO | - | - | deps: P2-19 |
| P2-21 | Full verification pass | TODO | - | - | deps: P2-20 |
| P2-22 | Phase 3 handoff | TODO | - | - | deps: P2-21 |
| P2-23 | Closeout and checkpoint | TODO | - | - | deps: P2-22 |

## Inputs recorded
REPO_URL, BASE_BRANCH=main, DOCS_PATH=`ai_calling agent/`, PYTHON=3.12, COVERAGE_MIN=90, COOKIE_SAMESITE=Lax, TRUSTED_PROXY_COUNT=1, PUSH=no.
`DASHBOARD_ORIGIN` left as an example placeholder (tests/docs only).

## Environment limits (this agent sandbox)
No PostgreSQL, Redis or Docker binaries found. DB-trigger, privilege (P2-17) and Redis-throttle tests are `PARTIAL` unless a local Postgres/Redis can be provisioned (see P2-01 notes).

## Iteration log
- P2-00: base gate passed (main contains phase-0 + phase-1 tips and backend/apps/core). Branch phase-2/identity-security created.
- P2-01: deps added and locked with hashes; pyjwt pinned to 2.15.0 (cooling-off + advisory). Next: P2-02 settings and environment.
- P2-02: auth settings, fail-fast rules, env docs, deploy check clean for prod+staging. Next: P2-03 user model extension (needs a local PostgreSQL for migration tests).
