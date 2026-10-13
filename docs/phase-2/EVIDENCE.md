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

## P2-05
- `pytest -q` (real PostgreSQL + Redis): 430 passed, coverage 100 % (963 statements; `apps/core`, `apps/accounts`, `config`). New: `test_permissions.py` (24), `test_scoping.py` (18), `test_scoping_lint.py`, extended `tests/test_default_deny.py`, settings isolation tests.
- Negative tests that show the guards fire: Campaign Manager -> `PUT /retry-policy/` 403 (Admin 200); Sales `POST`/`PATCH` 403; another manager's row -> 404 identical to a random UUID; superuser flag grants nothing (`has_perm` says True, `has_capability` False); `IsAuthenticated`-only view and a view without `HasCapability` are reported by the default-deny walk; a view bypassing `ScopedViewMixin` is reported by the lint; `ObjectScoped` hides foreign objects with 404.
- Mutation spot-checks (protection removed -> named tests fail, then restored):
  1. superuser bypass added to `capabilities()` -> `test_superuser_flag_does_not_bypass_rbac` FAILED.
  2. `ScopedViewMixin` stops calling `for_user` -> 4 scoping tests FAILED (own-rows list, 404 foreign detail, UUID-guess parity, cross-manager modify).
  3. permission errors fail open (`return True` in the exception branch) -> `test_errors_during_the_check_deny_and_log_without_secrets` FAILED.
- Process note: after mutation 3 the first full run reported 1 failure although the source matched its backup byte for byte. Cause (inferred, not proven): the mutation changed `False` to `True` (same file size) and the restore happened within the same second, so Python reused the stale `.pyc`. After deleting `__pycache__`, the suite passed 3 times in a row (430 passed). Future mutation checks clear bytecode caches first.
- The log record from the fail-closed test shows the Phase 1 redaction at work (`password=[REDACTED]` in the logged exception).
- `ruff`, `ruff format --check`, `mypy apps config scripts`: clean.

## P2-06
- `pytest -q --create-db` (real PostgreSQL + Redis): 544 passed; coverage 100 % (1147 statements; `apps/core`, `apps/accounts`, `apps/audit`, `config`). New tests: `tests/audit/` model layer (12), trigger layer (8), service (18), redaction (76, of which 69 are parametrized key x field cases).
- Trigger tests on real PostgreSQL 16: raw `UPDATE`, raw `DELETE`, `TRUNCATE` (also `TRUNCATE audit_event, accounts_user CASCADE`) each raise `append-only`; a blocked `UPDATE` of all rows changes nothing; raw `INSERT` still works; `pg_trigger` shows both triggers `tgenabled = 'A'`; dropping the trigger inside a rolled-back transaction lets the same `UPDATE` through (causality proof); migration `0002` reverses (no triggers, no function) and re-applies.
- Rollback on audit failure: `test_failed_audit_rolls_the_change_back` (refused audit write), `test_database_failure_during_the_audit_write_rolls_the_change_back` (DB error), `test_sync_roles_audit_failure_rolls_the_sync_back`.
- A genuine bug found by the redaction tests before it could ship: the Phase 1 rules did not mask `key_hash`; `key` and `key_hash` were added to the audit sensitive-key set.
- Mutation spot-checks (protection removed -> named tests fail; bytecode caches cleared; each restored and the full suite re-run: 544 passed):
  1. trigger no longer fires on UPDATE (DELETE only) -> `test_raw_update_is_blocked_by_the_trigger`, `test_a_blocked_update_of_every_row_changes_nothing` FAILED (only trigger tests; model tests unaffected).
  2. `record()` no longer requires a transaction -> `test_record_outside_a_transaction_is_refused` FAILED.
  3. audit-specific sensitive keys not passed to the redactor -> 28 redaction cases FAILED (`otp`, `code`, `totp`, `seed`, `key_hash`, ...).
  4. model `save()` guard removed -> `test_saving_an_existing_event_is_refused`, `test_manager_level_shortcuts_are_refused_too` FAILED (only model tests).
  A first attempt at (1) made the trigger fire on INSERT, which broke every test for the wrong reason; it was discarded and redone as above.
- The P2-03 migration test no longer uses `transaction=True` (flush would `TRUNCATE audit_event`; the trigger correctly refused it, observed in the failing run).
- `ruff`, `ruff format --check`, `mypy apps config scripts` (strict on `audit`): clean; `makemigrations --check`: no changes.
- Not verified here: layer 3 (privileges), P2-17.

## Phase 1 fix: regex performance guard (found during P2-06)
- Symptom: full suite occasionally "1 failed, 543 passed" (3 of ~14 runs), not reproducible on idle runs (8 of 8 passed).
- Reproduction: 4 busy-loop processes + `pytest tests/core/test_logging.py tests/core/test_health.py tests/test_celery_integration.py` -> `test_regex_performance_no_catastrophic_backtracking` FAILED once in 3 loaded runs; idle it takes ~1 s total.
- Fix: `time.process_time()` instead of `time.perf_counter()` (same 2 s bound). After the fix: 4 of 4 loaded runs passed; a catastrophic pattern still exceeds the bound (2.4 s CPU).
- Honest limit: the earlier failures were observed without a captured traceback (my first greps filtered the output), so the link between those runs and this test is inferred from the reproduction, not proven for each occurrence.

## P2-07
- `pytest -q` (real PostgreSQL + Redis): 631 passed, coverage 100 % (1346 statements; `apps/core`, `apps/accounts`, `apps/audit`, `config`). New: `tests/accounts/test_mfa.py` (46) and `tests/accounts/test_mfa_credential.py` (39), plus 2 restricted-credential tests in `test_permissions.py`.
- RFC 6238 Appendix B SHA-1 vectors (6 timestamps): `pyotp` 8-digit output equals the published values and our 6-digit configuration equals their last six digits. Seed built at runtime (no secret-looking literal committed).
- Window edges (-2 and +2 rejected, -1/0/+1 accepted), 11 malformed-input forms (incl. Unicode digits, trailing newline), replay (same code twice; older step after newer; enrolment code at login), failed attempts leave the replay marker untouched, other user's code rejected.
- Encrypted at rest: raw column starts `v1:` and neither the seed nor its lowercase appears anywhere in the whole row text; swapped ciphertext between two devices fails closed (`seed_unreadable`); undecryptable seed logs the device id only; key rotation re-seals under the new key id on next use.
- Enrolment: secret/URI returned once and hidden from `repr`; URI parsed (`otpauth://totp/...`, issuer, 160-bit secret); replacing a pending device; refusal when enrolled or inactive; audit events carry no secret; confirm activates + bumps epoch + audits; wrong code keeps it pending and is audited; DB rejects a second active or second pending device (partial unique indexes).
- Credential (service and HTTP via the test app): round trip, tamper, 8 garbage forms, expiry at exactly the lifetime (freezegun), other salt/other key, wrong content/purpose, epoch bump, use after confirmation, inactive/no-MFA-required/already-enrolled users; not a JWT in either direction; accepted only with the `MfaEnroll` scheme (other schemes ignored -> 401 + `WWW-Authenticate: MfaEnroll`); identical body for all bad tokens; normal session users refused by the enrolment endpoint; Admin's enrolment token gets 403 on a capability view; refused by ordinary endpoints; dead the moment enrolment is confirmed.
- Log/audit capture across begin, failed confirm, confirm, replay and token issue (DEBUG level): no seed, no URI, no code.
- Mutation spot-checks (protection removed -> named tests fail; bytecode caches cleared; full suite restored to 631 passed):
  1. replay check removed -> `test_a_code_cannot_be_used_twice`, `test_older_steps_are_refused_once_a_newer_one_was_used`, `test_the_enrolment_code_cannot_be_replayed_at_login` FAILED.
  2. window widened by one step -> `test_window_edges[-2-False]`, `[2-False]` FAILED.
  3. ciphertext not bound to the row -> `test_ciphertext_is_bound_to_its_own_row` FAILED.
  4. `HasCapability` ignores restricted credentials -> 3 tests FAILED (HTTP capability probe, unit, plain-request).
  5. enrolment token ignores the epoch -> `test_token_dies_when_the_session_epoch_moves`, `test_failures_are_uniform_for_every_kind_of_bad_token` FAILED. Note the post-confirmation test still passes under (5) because `must_enroll_mfa` independently rejects the token: two kill switches by design.
- Test-authoring mistakes found and fixed on the way (not product bugs): a parametrize name shadowing the `roles` fixture; `caplog.text` omits `extra` fields (read `record.device_id` instead); an expected exception not wrapped; my `decide()` helper built a plain Django request, exposing that `HasCapability` correctly **fails closed** when `request.auth` is absent (now covered by its own test).
- Intermittent failure, **unexplained**: one full `--cov` run showed "1 failed, 630 passed" and I filtered its output, so the failing test is unknown. It did not recur in 12 further full runs (4 with coverage, 3 after full PostgreSQL/Redis stop-start cycles, 5 under 3 busy-loop processes with runs of 64-68 s). Possibly the same load sensitivity fixed for the regex guard; not proven. From now on full output is captured to a file.
- `ruff`, `ruff format --check`, `mypy apps config scripts` (strict on `accounts`): clean; `makemigrations --check`: no changes (`0004_mfadevice`: one table, two partial unique indexes).
- Hygiene-gate catch: `git diff --cached --name-only` showed `backend/dump.rdb`, a Redis snapshot written by the sandbox's test Redis (started from `backend/`). Unstaged and deleted before any commit; `git log --all -- '*.rdb'` finds no commit containing one. The sandbox start script now runs Redis with `--dir /tmp --save ""`.
