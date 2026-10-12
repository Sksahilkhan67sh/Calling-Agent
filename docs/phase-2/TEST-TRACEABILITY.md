# Test traceability (Phase 2)

Source: `Testing/Test-Cases.xlsx` rows matching auth/MFA/lockout/RBAC/audit/security. Other matched rows (TC-1.06, TC-3.02, TC-3.04, TC-5.02, TC-SEC.06/07, TC-LOAD.*, TC-DG.*) are out of Phase 2 scope.

| Test case | Title | Implementing task | Covering tests |
|---|---|---|---|
| TC-AU.01 | MFA required for Admin and Campaign Manager | P2-07, P2-09 | P2-15 |
| TC-AU.02 | Refresh token is single-use | P2-08, P2-09 | P2-15 (refresh reuse, logout-then-reuse) |
| TC-AU.03 | Access token expires | P2-08 | P2-15 (expired token) |
| TC-AU.04 | Brute-force lockout and throttling | P2-10 | P2-15 (password/MFA brute force, stuffing) |
| TC-AU.05 | Default deny on every endpoint | P2-05 | existing test_default_deny extended |
| TC-AU.06 | Object-level scoping between Campaign Managers | P2-05 | P2-15 (IDOR → 404) |
| TC-AU.07 | Tokens in httpOnly cookies; CSRF enforced | P2-08, P2-09 | P2-15 (cookie attrs, CSRF) |
| TC-AU.08 | Django admin not exposed | P2-19, P2-20 | admin-absent test (URL resolve + INSTALLED_APPS) |
| TC-AU.09 | Deployment checks pass | P2-02, P2-21 | check --deploy --fail-level WARNING |
| TC-SEC.01 | Expired JWT rejected | P2-08 | P2-15 |
| TC-SEC.02 | Campaign Manager cannot write retry policy | P2-04, P2-05 | RBAC truth-table test (retry_policy.write); endpoint wiring Phase 3 |
| TC-SEC.03 | Full role x endpoint matrix | P2-04 | RBAC matrix test; per-endpoint rows extended in Phase 3+ |
| TC-SEC.04 | Rate limiting thresholds enforced | P2-10 | throttle tests; load-derived values stay OQ-01 |

Audit has no dedicated TC row; covered by Phase 2 tests in P2-06 (append-only at three layers, rollback on audit failure) per Security-Architecture §9.
