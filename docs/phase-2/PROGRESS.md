# Phase 2 progress

| ID | Task | Status | Evidence | Commit | Notes |
|---|---|---|---|---|---|
| P2-00 | Recon and scaffolding | DONE | EVIDENCE P2-00 | e22ab28 | deps: - |
| P2-01 | Dependencies (simplejwt, axes, pyotp) | DONE | EVIDENCE P2-01 | 241630d | deps: P2-00 |
| P2-02 | Settings and environment | DONE | EVIDENCE P2-02 | c4a65ef | deps: P2-01 |
| P2-03 | User model extension | DONE | EVIDENCE P2-03 | 2f10629 | deps: P2-02 |
| P2-04 | Roles, capabilities, RBAC matrix | DONE | EVIDENCE P2-04, P2-06 | 21b8d66, f023985 | deps: P2-03 |
| P2-05 | Permission classes and object scoping | DONE | EVIDENCE P2-05 | dce4947 | deps: P2-04 |
| P2-06 | audit app (append-only) | DONE | EVIDENCE P2-06 | f023985 | deps: P2-03 |
| P2-07 | MFA (TOTP) with encrypted seeds | DONE | EVIDENCE P2-07 | TBD | deps: P2-03, P2-06 |
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
PostgreSQL 16.15 and Redis 7.0 were installed with apt and started locally (no Docker, no systemd), so DB-trigger, privilege (P2-17) and Redis-throttle tests are runnable here.
Not available: Docker (compose stack), GitHub-hosted CI, network for pre-commit hook environments (gitleaks). Those stay `PARTIAL` with exact human commands.

## Iteration log
- P2-00: base gate passed (main contains phase-0 + phase-1 tips and backend/apps/core). Branch phase-2/identity-security created.
- P2-01: deps added and locked with hashes; pyjwt pinned to 2.15.0 (cooling-off + advisory). Next: P2-02 settings and environment.
- P2-02: auth settings, fail-fast rules, env docs, deploy check clean for prod+staging. Next: P2-03 user model extension (needs a local PostgreSQL for migration tests).
- P2-03: User extended (epoch, password_changed_at, full_name), automatic revocation on password change/deactivation, additive reversible migration. Next: P2-04 roles, capabilities, RBAC matrix.
- P2-04: capability registry (23), role matrix, `sync_roles` (idempotent, drift-removing), generated RBAC-MATRIX.md. PARTIAL only because the `rbac.sync` audit event needs the audit app (P2-06). Next: P2-05 permission classes and object-level scoping.
- P2-05: HasCapability (any-of, fail-closed, no superuser bypass), ScopedQuerySet/ScopedViewMixin/ObjectScoped, test-only app, default-deny extended. Next: P2-06 audit app (append-only at three layers); it also closes the `rbac.sync` audit event left open by P2-04.
- P2-06: audit app with model, trigger and (pending P2-17) privilege layers; audit.record/audited fail closed; redaction; `rbac.sync` event wired, which completes P2-04 (now DONE). Next: P2-07 MFA (TOTP) with encrypted seeds.
- P2-07: TOTP service (RFC 6238 vectors, +/-1 window, constant-time, replay-protected), seeds AES-GCM-encrypted and bound to their row, enrolment/confirm/reset, restricted `MfaEnroll` credential refused by HasCapability. HTTP-level restriction against real default authenticators is retested in P2-09/P2-15 (OQ2-13). Next: P2-08 cookie JWT authentication.
