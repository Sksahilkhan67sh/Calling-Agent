# Test traceability (Phase 2)

Source: `Testing/Test-Cases.xlsx` rows matching auth/MFA/lockout/RBAC/audit/security. Other matched rows (TC-1.06, TC-3.02, TC-3.04, TC-5.02, TC-SEC.06/07, TC-LOAD.*, TC-DG.*) are out of Phase 2 scope.

| Test case | Title | Implementing task | Covering tests |
|---|---|---|---|
| TC-AU.01 | MFA required for Admin and Campaign Manager | P2-07, P2-09 | `test_mfa_credential.py::test_must_enroll_follows_roles_until_a_device_is_active`, settings tests (prod requires Admin + Campaign Manager); login enforcement P2-09, attack tests P2-15 |
| TC-AU.02 | Refresh token is single-use | P2-08, P2-09 | `test_tokens.py::test_rotation_issues_a_new_pair_and_kills_the_old_refresh_token`, `::test_reusing_a_rotated_refresh_token_revokes_every_session`, `::test_logout_then_reuse_of_the_refresh_token_is_detected`; HTTP in P2-09/P2-15 |
| TC-AU.03 | Access token expires | P2-08 | `test_tokens.py::test_expired_access_token`, `test_cookie_auth.py::test_expired_cookie_gets_401` |
| TC-AU.04 | Brute-force lockout and throttling | P2-10 | P2-15 (password/MFA brute force, stuffing) |
| TC-AU.05 | Default deny on every endpoint | P2-05 | `tests/test_default_deny.py` (extended: HasCapability required, reviewed exceptions with justification) |
| TC-AU.06 | Object-level scoping between Campaign Managers | P2-05 | `tests/accounts/test_scoping.py` (list/detail/modify, UUID guessing -> 404); attack suite repeat in P2-15 |
| TC-AU.07 | Tokens in httpOnly cookies; CSRF enforced | P2-08, P2-09 | `test_cookies.py` (flags, prefixes, deletion), `test_cookie_auth.py` (CSRF 403); login/refresh responses in P2-09 |
| TC-AU.08 | Django admin not exposed | P2-19, P2-20 | admin-absent test (URL resolve + INSTALLED_APPS) |
| TC-AU.09 | Deployment checks pass | P2-02, P2-21 | check --deploy --fail-level WARNING |
| TC-SEC.01 | Expired JWT rejected | P2-08 | `test_tokens.py::test_expired_access_token`, `::test_expired_refresh_token`, `test_cookie_auth.py::test_expired_cookie_gets_401` |
| TC-SEC.02 | Campaign Manager cannot write retry policy | P2-04, P2-05 | `test_roles_matrix.py::test_only_admin_can_write_configuration_or_manage_suppression` (done); endpoint wiring Phase 3 |
| TC-SEC.03 | Full role x endpoint matrix | P2-04 | `test_roles_matrix.py::test_every_role_by_capability_cell` (role x capability, done); per-endpoint rows extended in Phase 3+ |
| TC-SEC.04 | Rate limiting thresholds enforced | P2-10 | throttle tests; load-derived values stay OQ-01 |

Audit has no dedicated TC row; covered by `tests/audit/` (model layer, trigger layer on real PostgreSQL, rollback on audit failure, redaction) per Security-Architecture §9. Privilege layer: P2-17.
