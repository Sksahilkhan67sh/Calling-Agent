# Phase 2 — Progress summary, P2-00 to P2-09

> **Partial progress report. Phase 2 is NOT complete** (10 of 24 tasks done). Everything below is taken from the
> repository (`PROGRESS.md`, `EVIDENCE.md`, `DECISIONS.md`, `OPEN-QUESTIONS.md`, `DOC-PATCHES.md`, `git log`) or from
> commands re-run when this file was written. Where something is not verified, it says so.

## 1. Overview

| Item | Value |
|---|---|
| Branch | `phase-2/identity-security` (from `main`, which contains merged Phase 0 and Phase 1) |
| Commits ahead of `main` | 22 before this document (23 with the commit that adds it) |
| Tasks done | **10 of 24**: P2-00 … P2-09 are `DONE` in `PROGRESS.md` (P2-04 was `PARTIAL` until P2-06 wired its audit event) |
| Tasks remaining | **14**: P2-10 … P2-23 |
| Files changed vs `main` | 97 before this document (77 added, 20 modified, 0 deleted); +7 235 / −512 lines |
| Tests | **868 passed, 0 failed, 0 skipped** (Phase 1 baseline recorded in `EVIDENCE.md` P2-01: 173 passed + 8 integration = 181) |
| Coverage | **100 %** of 1 761 statements; measured over `apps/core`, `apps/accounts`, `apps/audit`, `config` (omits `asgi.py`, `wsgi.py`, migrations); CI gate is 90 % |
| Push status | not pushed when this file was written; a draft PR is opened afterwards, on the user's explicit instruction. Nothing is merged. |

Commands used for the numbers above, **all re-run while writing this file** (PostgreSQL 16.15 and Redis 7.0 were
installed with `apt` in the agent sandbox; there is no Docker):

```bash
cd backend && . /tmp/cleanvenv/bin/activate        # venv from: pip install --require-hashes -r requirements/dev.txt
python -m pytest -q -p no:cacheprovider --cov --cov-report=term   # 868 passed; TOTAL 1761 statements, 0 missed, 100%
ruff check . ; ruff format --check .                                # clean (104 files)
mypy apps config scripts                                            # no issues in 61 files (strict on core, accounts, audit, config)
python manage.py makemigrations --check --dry-run --settings=config.settings.test   # No changes detected
pip-audit -r requirements/prod.txt -r requirements/dev.txt --require-hashes        # No known vulnerabilities found
bandit -q -r apps config -ll                                        # exit 0 (see note)
python scripts/check_api_contract.py                                # RESULT: FAIL (drift), see §3
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy --fail-level WARNING   # FAILS, 9 warnings, see below
```

**Checks that currently fail on this branch (reproduced locally, not yet seen on GitHub):**

1. **API contract check** (`contract` CI job): exit 1, 6 drift findings (§3).
2. **`check --deploy --fail-level WARNING`** (`deploy-check` CI job; prod and staging): 9 `drf_spectacular` warnings (W001 ×3: *could not resolve authenticator* for `CookieJWTAuthentication` on `LogoutView` and `EnrollmentTokenAuthentication` on the two enrolment views; W002 ×6: *unable to guess serializer* for the six `APIView`s in `apps/accounts/views.py`). This check was clean at P2-02 (`EVIDENCE.md` P2-02); the new views introduced the warnings. Both items are the OpenAPI annotation work planned for **P2-14**; they were not fixed here because this task was to summarise and open a draft PR, not to continue implementation.

*Note on bandit:* at the CI gate (`-ll`, medium severity and above) it exits 0. Run without `-ll` it lists 7 **low**-severity `B105` "hardcoded password" findings, all false positives on label constants (`bad_password`, `unusable_password`, the MFA encryption-context label and signing salt, and two audit action names). One was briefly misread as a failure while preparing this report; it is not.

## 2. Per-task summary

Test counts are per file, collected now (`pytest --collect-only`). "EVIDENCE" and "DECISIONS" refer to the `## P2-0x` sections of those files.

### P2-00 — Recon and scaffolding · commit `e22ab28`
- **Delivered:** `docs/phase-2/` skeleton (`PROGRESS.md` with P2-00…P2-23, `EVIDENCE.md`, `DECISIONS.md`, `OPEN-QUESTIONS.md`, `DOC-PATCHES.md`, `RBAC-MATRIX.md`, `AUTH-FLOWS.md`, `ENV-VARIABLES-DELTA.md`, `PHASE-3-HANDOFF.md`, `PR_DESCRIPTION.md`, `THREAT-MAPPING.md` placeholders) and `TEST-TRACEABILITY.md` mapping 13 auth/RBAC/security rows of `Test-Cases.xlsx` (TC-AU.01–09, TC-SEC.01–04) to tasks. Base gate passed: `main` contains the Phase 0 and Phase 1 tips and `backend/apps/core/`.
- **Tests:** none (documentation).
- **Evidence / decisions:** EVIDENCE P2-00; none.
- **Caveats:** the `Test-Cases.xlsx` scan matched 23 rows; 10 were judged out of Phase 2 scope (listed in `TEST-TRACEABILITY.md`). `AUTH-FLOWS.md`, `PHASE-3-HANDOFF.md`, `PR_DESCRIPTION.md`, `THREAT-MAPPING.md` are still placeholders (tasks P2-19, P2-20, P2-22, P2-23).

### P2-01 — Dependencies · commit `241630d`
- **Delivered:** `djangorestframework-simplejwt` 5.5.1, `django-axes` 8.3.1, `pyotp` 2.10.0, plus `pyjwt` 2.15.0 pinned explicitly (transitive of simplejwt); re-locked with hashes (`backend/requirements/{base,prod,dev}.{in,txt}`). Pin sets of base/prod/dev differ from Phase 1 only by these four additions.
- **Tests:** existing suite re-run (173 passed at that commit); `pip-audit` clean from a clean `--require-hashes` install.
- **Evidence / decisions:** EVIDENCE P2-01; DECISIONS P2-01 (release dates on PyPI).
- **Caveats:** `pyjwt` 2.15.1 (published 2026-09-28) was inside the 14-day cooling-off window and 2.14.0 has two advisories (PYSEC-2026-4141/4183), so 2.15.0 was pinned. `django-axes` is installed but **not wired until P2-10**. `pre-commit`/gitleaks could not run in the sandbox (no network for hook environments).

### P2-02 — Settings and environment · commit `c4a65ef`
- **Delivered:** `apps/accounts/roles.py` (role-name constants), `as_origins` validator in `apps/core/settings_utils.py`; settings in `config/settings/{base,dev,prod}.py` for JWT (HS256, issuer, audience fixed in code; lifetimes 900 s / 24 h), cookies (`__Host-`/`__Secure-` names, SameSite Lax|Strict, domain, tokens-in-body flag), credentialed CORS and CSRF origins, lockout and `TRUSTED_PROXY_COUNT`, MFA (roles, issuer, SHA-1/6 digits/30 s/±1 step), API-client write interval; `docs/phase-2/ENV-VARIABLES-DELTA.md`; updated `scripts/gen_throwaway_env.py`.
- **Tests:** `tests/config/test_settings_auth.py` (52 now; 48 when written). Negative tests: `test_algorithm_cannot_be_changed_by_environment`, `test_prod_refuses_wildcard_plaintext_or_path_origins`, `test_credentialed_cors_requires_explicit_origins_in_prod`, `test_prod_requires_mfa_for_admin_and_campaign_manager`, `test_mfa_roles_reject_unknown_names_and_allow_extra_roles`, `test_prod_rejects_out_of_range_auth_values` (SameSite `None` refused, bounds); the Phase 1 fail-fast test now also covers the five newly required prod variables.
- **Evidence / decisions:** EVIDENCE P2-02; DECISIONS P2-02 (refresh lifetime 24 h as idle timeout; SameSite Lax needs same-site dashboard and API; cookie names; SHA-1 for authenticator compatibility).
- **Caveats:** at that commit `check --deploy` was clean for prod and staging (no longer true, see §1). Axes settings are defined but unused until P2-10.

### P2-03 — User model extension · commit `2f10629`
- **Delivered:** `User.full_name`, `auth_epoch`, `password_changed_at`, `bump_auth_epoch()`; automatic epoch bump on password change and deactivation inside `save()`; migration `apps/accounts/migrations/0002_user_epoch_and_profile.py` (additive, reversible, `db_default` so an older app version can still insert); password-similarity validator now checks `email` and `full_name`.
- **Tests:** `tests/accounts/test_user_model.py` (26). Proves: `test_stale_copy_cannot_roll_the_epoch_back`, `test_bumps_are_relative_increments_not_absolute_writes`, `test_epoch_cannot_be_written_through_update_fields`, `test_deactivation_bumps_but_reactivation_and_resave_do_not`, `test_saving_a_deleted_user_does_not_resurrect_it`, `test_inactive_user_cannot_authenticate`, the password-validator cases, and `test_migration_0002_applies_over_phase1_data_and_reverses` (including an insert the way older code would do it).
- **Evidence / decisions:** EVIDENCE P2-03; DECISIONS P2-03 (monotonic epoch, `FOR UPDATE` comparison in `save()`, `db_default`).
- **Caveats:** `QuerySet.update()` bypasses the `save()` hooks (used deliberately for hash upgrades in P2-09). Role-change revocation (group membership) is P2-11 and **not yet implemented**; `must_enroll_mfa` was completed in P2-07.

### P2-04 — Roles, capabilities, RBAC matrix · commits `21b8d66` (+ `f023985` for the audit event)
- **Delivered:** capability registry (23 capabilities, `client_grantable` flag) and `ROLE_CAPABILITIES` for Admin, Campaign Manager, Sales / Follow-up, System in `apps/accounts/roles.py`; capabilities as custom permissions (`apps/accounts/migrations/0003_capability_permissions.py`, metadata only); `apps/accounts/services.py::sync_roles` and `manage.py sync_roles` (idempotent, removes drift, one `rbac.sync` audit event only when something changed); `scripts/gen_rbac_matrix.py` generating `docs/phase-2/RBAC-MATRIX.md`.
- **Tests:** `tests/accounts/test_roles_matrix.py` (109), `test_sync_roles.py` (9). Proves: hand-written role × capability truth table (`test_role_capabilities_match_the_reviewed_truth_table`, `test_every_role_by_capability_cell`), `test_only_admin_can_write_configuration_or_manage_suppression`, `test_sensitive_capabilities_belong_to_no_role`, `test_api_clients_can_only_be_granted_read_only_cross_scope_capabilities`, generated-doc drift test, `test_second_run_is_a_no_op`, `test_drift_is_repaired_in_both_directions`, `test_missing_permission_fails_closed`, `test_sync_roles_audit_failure_rolls_the_sync_back`.
- **Evidence / decisions:** EVIDENCE P2-04 (and P2-06 for the audit part); DECISIONS P2-04 (safer reading where docs conflict: no role holds `recordings.listen`/`transcripts.view` by default; `contacts.suppress` for Campaign Manager; Sales limited to scoped contact view + Final Output).
- **Caveats:** these are product calls awaiting confirmation (OQ2-04, OQ2-05, OQ2-06). `users.manage` and `api_clients.manage` are held by no role (management commands only in Phase 2). The management commands for users/clients (P2-13) do not exist yet.

### P2-05 — Permission classes and object-level scoping · commit `dce4947`
- **Delivered:** `apps/accounts/permissions.py` (`HasCapability(*names)` any-of, `ObjectScoped`, later `IsEnrollmentCredential`), `apps/accounts/querysets.py` (`ScopedQuerySet.for_user`, `ScopedViewMixin`), `User.capabilities()` / `has_capability()` (ignore `is_superuser`), test-only app `tests/testapp/` (installed only by test settings) with a real migration, extension of `tests/test_default_deny.py` (reviewed-exceptions dict with written justifications).
- **Tests:** `test_permissions.py` (26), `test_scoping.py` (18), `test_scoping_lint.py` (4). Attack/negative: `test_superuser_flag_does_not_bypass_rbac`, `test_guessing_a_uuid_is_indistinguishable_from_a_foreign_row` (404, identical body), `test_cannot_modify_another_managers_row`, `test_privilege_escalation_to_admin_capability_is_refused`, `test_sales_cannot_write_or_list_campaign_data`, `test_recordings_need_an_explicit_per_user_grant`, `test_errors_during_the_check_deny_and_log_without_secrets` (fail closed), `test_non_boolean_answers_are_not_trusted`, `test_object_scoped_backstop_hides_foreign_objects`, `test_lint_detects_a_view_that_bypasses_scoping`; default-deny negatives for an undeclared and an `IsAuthenticated`-only view.
- **Evidence / decisions:** EVIDENCE P2-05; DECISIONS P2-05.
- **Caveats:** the scoping lint detects views through a class-level `queryset` attribute only (OQ2-07). A single `HasCapability` cannot vary by HTTP method. No real business model uses `for_user` yet (Phase 3). One post-mutation full run showed a failure caused by a stale `.pyc` (inferred, not proven); bytecode caches are cleared before every mutation run since.

### P2-06 — `audit` app (append-only) · commit `f023985`
- **Delivered:** `apps/audit/` (`models.py`, `service.py`, `redaction.py`, `apps/audit/actions.py`, `context.py`), migrations `apps/audit/migrations/0001_initial.py` and `0002_append_only_triggers.py`; `audit.record()` (must run inside `transaction.atomic()`) and `audited()`; `Actor` helpers incl. `system:cli:<os-user>`.
- **Tests:** `tests/audit/` — `test_model_layer.py` (12), `test_triggers.py` (8, real PostgreSQL), `test_service.py` (18), `test_redaction.py` (76). Proves: raw `UPDATE`/`DELETE`/`TRUNCATE` blocked by the trigger (`test_raw_update_is_blocked_by_the_trigger`, `test_truncate_is_blocked_by_the_trigger`), triggers are `ENABLE ALWAYS` (`test_triggers_are_enabled_always_so_replication_mode_cannot_skip_them`), the trigger is the cause (`test_it_is_the_trigger_that_protects_the_row_not_something_else`), `test_failed_audit_rolls_the_change_back`, `test_database_failure_during_the_audit_write_rolls_the_change_back`, `test_record_outside_a_transaction_is_refused`, secret keys masked in before/after/metadata (`test_secret_keys_are_masked_in_every_payload_field`), `test_a_blocked_update_of_every_row_changes_nothing`.
- **Evidence / decisions:** EVIDENCE P2-06; DECISIONS P2-06 (three layers; no foreign keys; redaction; `flush` refused).
- **Caveats:** **layer 3 (INSERT/SELECT-only privileges, `deploy/sql/roles.sql`) is NOT implemented**; that is P2-17. The table owner or a superuser can still drop the trigger (tested as the proof of causality). Client IP and user agent are empty until P2-10 binds the trusted-proxy resolver. Django's `flush` and `transaction=True` tests are impossible by design.
- **Found on the way:** the redaction test showed the Phase 1 rules did not mask `key_hash`; `key` and `key_hash` were added. A load-sensitive Phase 1 test was fixed in a separate commit (`d9315a1`, §5).

### P2-07 — MFA (TOTP) with encrypted seeds · commit `bb05736`
- **Delivered:** `apps/accounts/mfa.py` (RFC 6238 on `pyotp`, enrol/confirm/verify/reset, restricted enrolment token), `MfaDevice` (migration `apps/accounts/migrations/0004_mfadevice.py`, one active and one pending device per user as partial unique indexes), `EnrollmentTokenAuthentication` and `IsEnrollmentCredential`, `User.must_enroll_mfa`; `HasCapability` refuses any `restricted` credential.
- **Tests:** `test_mfa.py` (46), `test_mfa_credential.py` (39). Proves: RFC 6238 SHA-1 vectors (`test_rfc6238_sha1_vectors`), `test_window_edges`, replay (`test_a_code_cannot_be_used_twice`, `test_older_steps_are_refused_once_a_newer_one_was_used`, `test_the_enrolment_code_cannot_be_replayed_at_login`), `test_the_seed_is_never_stored_in_plaintext`, `test_ciphertext_is_bound_to_its_own_row`, `test_unreadable_seed_fails_closed_and_logs_without_secrets`, `test_key_rotation_reseals_the_seed_on_next_successful_use`, `test_malformed_codes_are_rejected_without_touching_the_device`, token tests (`test_token_is_not_a_jwt_and_a_jwt_is_not_an_enrolment_token`, `test_token_cannot_be_used_after_enrolment_is_confirmed`), `test_the_credential_never_grants_role_capabilities`, `test_no_seed_uri_or_code_reaches_logs_or_audit`.
- **Evidence / decisions:** EVIDENCE P2-07; DECISIONS P2-07 (own TOTP with encrypted seeds, not `django-otp`; ciphertext bound to the device row; `MfaEnroll` header credential).
- **Caveats:** no recovery codes, SMS or multiple devices (OQ2-12). TOTP uses the server clock (OQ2-14). One full coverage run failed once with its output unseen; not reproduced in 12 later runs (`EVIDENCE.md` P2-07; cause unknown).

### P2-08 — Cookie JWT authentication · commit `b488051`
- **Delivered:** `apps/accounts/tokens.py` (issue/read/rotate/revoke, reuse detection), `cookies.py`, `CookieJWTAuthentication` + `enforce_csrf` in `authentication.py`; `rest_framework_simplejwt.token_blacklist` installed; `DEFAULT_AUTHENTICATION_CLASSES` switched to `CookieJWTAuthentication`; `tests/accounts/forge.py` builds attacker tokens from per-run throwaway keys.
- **Tests:** `test_tokens.py` (72), `test_cookie_auth.py` (29), `test_cookies.py` (13). Attack/negative: `test_forged_and_malformed_tokens_are_rejected` (16 forms incl. `alg=none`, RS256, HS512 with the right key, **HS256 signed with a public key as secret**, tampering), `test_tokens_missing_any_required_claim_are_rejected`, `test_validly_signed_but_malformed_claims_are_rejected` (19 variants), `test_a_refresh_token_is_not_an_access_token_and_vice_versa`, `test_user_state_changes_kill_access_tokens`, `test_roles_claim_is_ignored_for_authorisation`, `test_reusing_a_rotated_refresh_token_revokes_every_session`, `test_logout_then_reuse_of_the_refresh_token_is_detected`, `test_a_correctly_signed_token_we_never_issued_is_refused`, `test_only_a_digest_of_the_refresh_token_is_stored`, `test_unsafe_methods_need_the_csrf_token_under_cookie_auth`, `test_bearer_header_is_ignored_when_tokens_in_body_is_off`, `test_an_invalid_bearer_never_falls_back_to_a_valid_cookie`, `test_every_failure_looks_identical_to_the_client`, cookie flag/prefix/deletion tests.
- **Evidence / decisions:** EVIDENCE P2-08; DECISIONS P2-08 (refresh tokens stored only as SHA-256 digests, unlike stock SimpleJWT; reuse = theft; Bearer only in body mode).
- **Caveats:** parallel refresh calls look like theft and sign the user out everywhere (OQ2-15); the access token outlives a plain logout by up to 15 min (OQ2-16); `flushexpiredtokens` works but is **not scheduled** (OQ2-18). **A real bug was found by the tests and fixed:** `select_for_update().select_related("user")` on a nullable FK made PostgreSQL refuse the lock, which would have broken every token refresh.

### P2-09 — Auth endpoints · commit `aa2bae0`
- **Delivered:** `apps/accounts/{login,parsers,serializers,views,urls}.py`; routes under `/v1/auth/`: `POST token`, `POST token/refresh`, `POST logout`, plus `GET csrf`, `POST mfa/enroll`, `POST mfa/confirm`; `config/urls.py` includes them. Own credential check with equalised work; CSRF-first refresh; fail-closed audit; JSON-only 8 KiB parser; strict serializers; `Cache-Control: no-store` on every auth response; the six views added to the default-deny reviewed exceptions with justifications.
- **Tests:** `test_auth_login.py` (24), `test_auth_session.py` (21), `test_auth_enrollment.py` (17), `test_auth_input.py` (58). Attack/negative: `test_every_failure_is_the_same_response`, `test_every_failure_path_performs_exactly_one_password_verification` (deterministic equalised work), `test_unknown_user_and_wrong_password_take_comparable_time_under_argon2` (statistical, marker `timing`), `test_hash_upgrade_does_not_sign_the_user_out`, `test_a_password_typed_into_the_email_field_is_never_stored`, `test_a_failed_audit_write_means_no_session`, `test_refresh_without_the_csrf_header_is_403_and_does_not_rotate`, `test_replaying_a_rotated_refresh_token_is_theft_over_http`, `test_logout_never_revokes_someone_elses_refresh_token`, `test_users_who_must_enrol_get_a_restricted_credential_and_no_session`, `test_the_enrolment_endpoints_refuse_everything_but_the_restricted_credential`, `test_unknown_fields_are_rejected_without_being_echoed`, `test_oversized_bodies_are_413_without_reading_them_all`, `test_null_bytes_are_rejected_before_they_reach_the_database`, `test_lone_surrogates_sent_as_json_escapes_never_become_a_500`, `test_login_is_rate_limited_per_client_with_retry_after`.
- **Evidence / decisions:** EVIDENCE P2-09; DECISIONS P2-09; DOC-PATCHES "From P2-09".
- **Caveats:** **no lockout yet** (P2-10): the `login` throttle (keyed on `REMOTE_ADDR`/`NUM_PROXIES`) is the only brute-force control on these endpoints. OpenAPI annotations and the contract check are P2-14 (§3). The Django test client sends every cookie to every path, so the refresh cookie's `Path=/v1/auth/` is verified by attribute tests, not by browser behaviour. Error bodies follow the contract's `{code, message}` while the global Phase 1 handler still returns `{detail}` (OQ2-20).

## 3. Contract status

`python scripts/check_api_contract.py`, run now, prints: *contract operations compared: 3; not yet implemented (informational): 18; internal, not in the contract: /healthz, /readyz* and then **`RESULT: FAIL (drift)`** with these 6 findings:

| Finding | What it means |
|---|---|
| `POST /auth/token: response codes missing in implementation: ['401','429']` | The endpoint returns 200/401/429 (all exercised by tests), but the generated OpenAPI schema does not yet declare 401/429. |
| `POST /auth/token/refresh: ... missing ['401']` | Same: 200 and 401 are implemented and tested; schema annotation missing. |
| `POST /auth/logout: ... missing ['204']` | 204 is implemented and tested; schema annotation missing. |
| `GET /auth/csrf: implemented but not defined in the contract` | Added beyond the contract. |
| `POST /auth/mfa/enroll: ... not defined in the contract` | Added beyond the contract. |
| `POST /auth/mfa/confirm: ... not defined in the contract` | Added beyond the contract. |

**So none of the three contract paths is yet *verified* to match the spec by the project's own checker.** What can be said is that the behaviours the spec lists for them are implemented and tested, and that the mismatch is in the OpenAPI annotations, which is P2-14's job (with the three paths then made blocking in CI).

Beyond the contract (and beyond its documented statuses): `GET /auth/csrf`, `POST /auth/mfa/enroll`, `POST /auth/mfa/confirm`, plus extra statuses on the contract paths (400, 403, 413, 415, `Set-Cookie`/`Retry-After` headers, `X-CSRFToken` requirement on refresh and logout). These are written up in `DOC-PATCHES.md` under the headings **"From P2-07"** and **"From P2-09"**. (`DOC-PATCHES.md` entries do not carry numeric IDs; those two headings are the references.)

## 4. Mutation checks (protection removed, named tests fail, then restored)

33 protections were each removed once and shown to fail their tests (full suite re-run green after each restore):

- **P2-03 (2):** `save()` writes `auth_epoch` again; deactivation no longer bumps.
- **P2-04 (2):** Campaign Manager gains `retry_policy.write`; `sync_roles` stops removing drift.
- **P2-05 (3):** superuser bypasses capabilities; `ScopedViewMixin` skips `for_user`; permission errors fail open.
- **P2-06 (4):** trigger no longer blocks UPDATE; `record()` no longer requires a transaction; audit-specific sensitive keys not applied; model `save()` guard removed.
- **P2-07 (5):** replay check removed; window widened; ciphertext not bound to the row; `HasCapability` ignores restricted credentials; enrolment token ignores the epoch.
- **P2-08 (8):** `token_type` not checked; epoch not compared; `is_active` not checked; CSRF not enforced; reuse not acted on; plaintext refresh token stored; Bearer honoured when the mode is off; invalid Bearer falls back to the cookie.
- **P2-09 (9):** unknown user skips the dummy hash; distinct response for inactive users; refresh skips CSRF; hash upgrade via `save()`; logout revokes any token; body limit removed; responses cacheable; audit label stores any text; unknown fields accepted.

**Mutations that did not apply or were invalid the first time (all redone, per `EVIDENCE.md`):** P2-04 mutation 1 hit the registry tuple instead of the role set; P2-06 mutation 1 made the trigger fire on INSERT (broke every test for the wrong reason); P2-09 mutation 8 did not apply because ruff had re-wrapped the target line, and a half-applied edit of mine had left a failing baseline test that the first P2-09 mutation run exposed (fixed, baseline re-verified green: 868 passed). One stale-`.pyc` incident after a same-size mutation (P2-05) is noted under P2-05.

## 5. Changes to Phase 0 / Phase 1 files

Nothing under `docs/phase-0/`, `spike/` or the design documents was touched. 20 pre-existing files were modified:

| File | Why | Commit(s) |
|---|---|---|
| `backend/requirements/{base.in,base.txt,dev.txt,prod.txt}` | four new pins, hashed re-lock | `241630d` |
| `backend/apps/core/settings_utils.py` | `as_origins` validator | `c4a65ef` |
| `backend/config/settings/{base,dev,prod}.py` | auth/cookie/CORS/lockout/MFA settings and prod fail-fast; later `apps.audit`, `token_blacklist`, default authenticator, password-validator options | `c4a65ef`, `2f10629`, `f023985`, `b488051` |
| `backend/config/settings/test.py` | install the test-only app | `dce4947` |
| `backend/config/urls.py` | include `/v1/auth/` routes | `aa2bae0` |
| `backend/pyproject.toml` | strict mypy and coverage for `accounts`/`audit`, `S105` ignore for `apps/audit/actions.py`, `security`/`timing` markers | `2f10629`, `f023985`, `aa2bae0` |
| `backend/scripts/gen_throwaway_env.py` | the five newly required prod variables (CI deploy-check needs them) | `c4a65ef` |
| `backend/apps/accounts/models.py` | the Phase 1 `User` extended (epoch, capabilities, MFA, `Meta.permissions`) | `2f10629`, `21b8d66`, `dce4947`, `bb05736` |
| `backend/apps/core/logging.py` | `user_id` added to the allowed log-context fields | `3ca968e` |
| `docs/phase-1/ENV-VARIABLES.md` | new variables and tightened rules (the env-drift test reads this file; the P2-02 task asked for it) | `c4a65ef` |
| `backend/tests/conftest.py`, `tests/config/test_settings.py` | new required prod variables; JWT key ≥ 50; default authenticator assertion | `c4a65ef`, `b488051` |
| `backend/tests/core/test_exceptions_permissions.py`, `tests/test_default_deny.py` | with a real authenticator an anonymous call is `401`, not `403` (intent unchanged: authenticated callers still get the `403`); reviewed-exceptions dict; view counts | `b488051`, `dce4947`, `bb05736`, `aa2bae0` |
| `backend/tests/core/test_logging.py` | `user_id` context test; the regex-performance guard now measures CPU time (it failed intermittently under CPU load) | `3ca968e`, `d9315a1` |

## 6. Open questions needing a human decision

All 23 are in `OPEN-QUESTIONS.md`. Recommendations below are mine, not decisions.

**Decide before real users or production:**

| ID | Question | Recommendation |
|---|---|---|
| **OQ2-19** | A user whose roles require MFA but who has not enrolled gets the enrolment credential on a correct password alone, so someone who learns the password first can enrol their own authenticator. | Highest priority. Require an out-of-band one-time enrolment code printed by the provisioning command and checked at `/auth/mfa/enroll`; at minimum make `bootstrap_admin`/`create_user` hand over a one-time password and require immediate enrolment. |
| **OQ2-01** | No absolute session lifetime (rotation makes 24 h an idle timeout). | Add an absolute cap (suggest 12 h for Admin and Campaign Manager) via an `auth_time` claim carried through rotation. |
| **OQ2-03** | Dashboard and API domains (`DASHBOARD_ORIGIN` input is still an example). | Confirm real hostnames; keep `SameSite=Lax` only if they share a registrable domain (e.g. `dashboard.x.com` and `api.x.com`); otherwise revisit cookies and CSRF together. |
| **OQ2-20** | Contract error shape `{code, message}` vs the global handler's `{detail}`. | Move the global handler to the contract shape in one dedicated change before Phase 3 multiplies endpoints. |
| **OQ2-21** | The contract has no `GET /me`; the SPA cannot learn the user's name or roles after login. | Add it (authentication only, no capability). |
| **OQ2-22** | Logout needs a valid access token, so after it expires the refresh cookie lingers. | Let logout work from the refresh cookie alone (CSRF-protected). |
| **OQ2-23** | Login, refresh and enrolment share one throttle bucket per client address (shared NAT). | Keep; rely on the per-account lockout (P2-10) and set rates from load tests. |
| OQ2-04 | `recordings.listen` / `transcripts.view` held by no role by default. | Keep (least privilege); add an audited per-user grant command. |
| OQ2-05 | Meaning of "assigned" scope for Sales / Follow-up; attempt history in the contact view. | Assignment-based scope defined in Phase 3; Sales sees no attempt history by default. |
| OQ2-06 / OQ2-10 | No workflow to grant a capability to one user; such grants must be audited. | A `grant_capability` command, audited, before Phase 5/6. |
| OQ2-08 | Audit retention, export, tamper-evidence, partitioning. | Decide a retention period and an external immutable export (e.g. object-lock storage) before production. |
| OQ2-12 | No recovery codes, multiple devices or voluntary enrolment. | Start with the audited `mfa_reset` command under a two-person process; add recovery codes later. |
| OQ2-15 | Parallel refresh looks like theft. | Frontend must serialise refresh calls; do not add a grace window. |
| OQ2-16 | Access token outlives logout by up to 15 min. | Accept for the MVP; add a per-session denylist or shorten the access lifetime if the risk appetite is lower. |

**Engineering follow-ups (no human decision needed):** OQ2-02 (rate values from load tests, Phase 8), OQ2-07 (scoping lint limits, Phase 3), OQ2-09 (client IP in audit, closed by P2-10), OQ2-11 (load-sensitive Phase 1 tests: watch CI), OQ2-13 (retest enrolment-credential restriction in P2-15), OQ2-14 (NTP on app hosts: operations), OQ2-17 (per-request DB cost: only if measured), OQ2-18 (schedule `flushexpiredtokens` with the Phase 4 worker).

## 7. Production impact

- **Five variables become required in prod/staging** (the app refuses to start without them): `CORS_ALLOWED_ORIGINS` (non-empty, `https://` only), `CSRF_TRUSTED_ORIGINS` (non-empty, `https://` only), `AXES_FAILURE_LIMIT`, `TRUSTED_PROXY_COUNT`, `LOGIN_RATE_LIMIT_PER_MINUTE`. (`AXES_FAILURE_LIMIT` and `TRUSTED_PROXY_COUNT` are required now but only used from P2-10.)
- **`JWT_SIGNING_KEY` minimum length rises from 32 to 50 characters** in prod/staging (and must differ from `DJANGO_SECRET_KEY`).
- Thirteen variables are new in total: ten are optional with defaults (JWT lifetimes, cookie SameSite/domain, tokens-in-body, axes cool-off, MFA settings, API-client write interval) and three (`CSRF_TRUSTED_ORIGINS`, `AXES_FAILURE_LIMIT`, `TRUSTED_PROXY_COUNT`) are among the five required ones above. Two further variables (`CORS_ALLOWED_ORIGINS`, `LOGIN_RATE_LIMIT_PER_MINUTE`) already existed but are now required in prod. See `docs/phase-2/ENV-VARIABLES-DELTA.md` and `docs/phase-1/ENV-VARIABLES.md`.
- **Migrations (all additive):** `accounts` 0002, 0003 (metadata only), 0004; `audit` 0001, 0002 (**installs triggers on `audit_event`**); SimpleJWT `token_blacklist` tables. The audit triggers make `manage.py flush` and `TRUNCATE` on that table fail by design; rolling the audit migration back needs the reverse SQL (drops the triggers; reviewer/operator only).
- **Behaviour changes:** all endpoints except health now use cookie JWT authentication by default (anonymous callers get `401`); the dashboard and API must be same-site for `SameSite=Lax` cookies; the dashboard must send `X-CSRFToken` on unsafe requests and serialise refresh calls.
- **Operations to arrange:** run `python manage.py flushexpiredtokens` on a schedule (not yet scheduled); NTP on all app hosts (TOTP).

## 8. Not verified here, with the reviewer's command

| Not verified | Why | Command |
|---|---|---|
| **GitHub-hosted CI (all jobs)** | not visible from the sandbox before the PR run; two jobs are **expected to fail** (contract, deploy-check) per §1 | check the PR's Checks tab |
| `pre-commit` hooks | hook environments need network access that the sandbox lacks | `pre-commit run --all-files` |
| gitleaks as run by CI | CI uses a pinned `gitleaks-action`; here a manually downloaded `gitleaks` 8.30.1 binary was used (its checksum was **not** verified against the release checksums) | `gitleaks git --log-opts="main..HEAD" --config .gitleaks.toml` |
| Docker image and compose smoke test | no Docker in the sandbox | `docker build -f docker/Dockerfile -t calling-agent-api:ci .` then `cp .env.example .env && docker compose --env-file .env -f docker/compose.dev.yml up -d --build` and `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/readyz` |
| API contract check | fails today (§3) | `cd backend && python scripts/check_api_contract.py` |
| `check --deploy` | fails today (§1) | `cd backend && set -a; eval "$(python scripts/gen_throwaway_env.py)"; set +a; DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy --fail-level WARNING` |
| Real browser behaviour (cookie `Path`, `SameSite`, `Secure`, `__Host-` acceptance, CSRF double-submit) | the Django test client sends all cookies to all paths | manual: log in from a browser against a TLS deployment and inspect cookies |
| Concurrency (parallel refresh, concurrent first `sync_roles`) | tests are sequential; row locks are reasoned, not stress-tested | a threaded test against PostgreSQL in CI |
| Statistical timing test | uses real Argon2, median of 15, window 0.5×–2×; the deterministic call-count test is the real guarantee | `pytest -m timing` |
| Privilege layer of the audit protection | not implemented (P2-17) | `psql -f deploy/sql/roles.sql` (after P2-17) |
| One unexplained single test failure | one coverage run failed with its output not captured (P2-07); not reproduced in 12 later runs | repeat `pytest --cov` several times in CI |

## 9. Remaining work (P2-10 … P2-23)

- **P2-10** Lockout (django-axes on failed password and MFA), trusted-proxy client IP, throttle scopes against real Redis.
- **P2-11** Session revocation semantics: epoch bump on password change, role change, MFA reset, deactivation, logout-everywhere.
- **P2-12** Machine clients (`ApiClient`): hashed shown-once keys, scopes via `client_grantable`, revocation, last-used interval, throttle, cookie-vs-key precedence.
- **P2-13** Management commands: `bootstrap_admin`, `create_user`, `assign_role`, `deactivate_user`, `mfa_reset`, API-client commands (audited, non-interactive).
- **P2-14** OpenAPI annotations and the blocking contract check for the three auth paths (fixes both failing checks in §1).
- **P2-15** Attack-oriented `tests/security/` suite (≥ 5 mutation spot-checks recorded).
- **P2-16** Logging and redaction verification across the full auth flows.
- **P2-17** `deploy/sql/roles.sql` and the privilege layer of audit immutability, with integration tests.
- **P2-18** CI updates (security job, blocking contract paths, actionlint); stays `PARTIAL` until a green PR run is seen.
- **P2-19** Documentation: `AUTH-FLOWS.md`, `RBAC-MATRIX.md`, README additions (bootstrap admin, enrol MFA, run the security suite).
- **P2-20** Security self-review and `THREAT-MAPPING.md`.
- **P2-21** Full verification pass from a clean clone.
- **P2-22** `PHASE-3-HANDOFF.md`.
- **P2-23** Closeout: re-verify, checkpoint commit and local tag; `PHASE_2_COMPLETE`.

## Corrections to earlier records

- `EVIDENCE.md` P2-02 says "+53 tests in `tests/config/test_settings_auth.py`". More precisely: that file had 48 tests when written (it has 52 now after P2-05 added 4) and the other 5 were new parametrized cases in the Phase 1 `test_settings.py`. `EVIDENCE.md` was not edited.
- `EVIDENCE.md` P2-02 records `check --deploy` as clean; that was true at that commit and is **not** true on the branch tip (§1).
