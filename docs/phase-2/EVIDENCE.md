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

## P2-08
- `pytest -q` (real PostgreSQL + Redis): 748 passed, coverage 100 % (1517 statements). New: `test_tokens.py` (72), `test_cookie_auth.py` (29), `test_cookies.py` (13) + `forge.py` helper; Phase 1 tests adapted: 3 default-deny tests (401 for anonymous, 403 for authenticated), the `DEFAULT_AUTHENTICATION_CLASSES` assertion, `user_id` context test (separate commit `3ca968e`).
- Forgery matrix (all rejected, service and HTTP): `alg=none` (with and without trailing dot), wrong key, HS512 with the right key (wrong algorithm), RS256, **HS256 signed with an RSA public key as the HMAC secret (key confusion)**, tampered `sub`/`auth_epoch`/`token_type`, flipped signature, truncated, empty, `..`, not a JWT, five parts, 5 000-character token; each of the 8 required claims removed; wrong `iss`/`aud`; 19 malformed-claim variants (string/bool/float epoch, non-UUID `sub`, empty `jti`, string/bool `exp`, string/bool/future `iat`). A control test shows a correctly built token *with the real key* is accepted, so every rejection is caused by the single thing it varies. An `aud` list that includes ours is accepted (valid per RFC 7519; test documents it).
- Status codes: no cookie / forged / expired / wrong type / epoch mismatch / deactivated / deleted -> 401 with identical bodies; valid token + missing, absent-cookie or mismatching CSRF -> 403; GET/HEAD/OPTIONS need no CSRF; Bearer ignored when off, no-CSRF and wins over cookie when on, invalid Bearer never falls back.
- Rotation: chain of rotations; reuse -> every session dead (other session, the newest rotated token), audit event with `jti` only, WARNING log with `user_id`/`jti` only and no token or email in the log text, epoch survives the failed request; logout-then-reuse detected; revoke idempotent and silent for garbage and for validly-signed never-issued tokens; stale-epoch / inactive / unknown / expired / deleted-user tokens are plain-invalid without escalation; `flushexpiredtokens` works on digest rows.
- Storage: raw refresh token appears nowhere in `token_blacklist_outstandingtoken`; access tokens are never stored.
- **Real bug found by the tests before it shipped:** `select_for_update().select_related("user")` on `OutstandingToken` (nullable `user`) made PostgreSQL refuse the lock (`FOR UPDATE cannot be applied to the nullable side of an outer join`), so **every token refresh would have failed**. Fixed with `select_for_update(of=("self",))`.
- Dead code removed after coverage showed it unreachable (`_handle_reuse(None)`); two missing branches got tests (`iat: true`, revoking a never-issued token). Coverage 100 %.
- Mutation spot-checks (protection removed -> named tests fail; bytecode cleared; restored; full suite 748 passed):
  1. `token_type` not checked -> 7 failures (type-confusion tests in service and HTTP, `missing token_type`).
  2. epoch not compared -> 4 failures. 3. `is_active` not checked -> 2 failures. 4. CSRF not enforced -> 2 failures.
  5. reuse not acted on -> 3 failures. 6. plaintext refresh token stored -> `test_only_a_digest_of_the_refresh_token_is_stored` fails.
  7. Bearer honoured when the mode is off -> 1 failure. 8. invalid Bearer falls back to the cookie -> 1 failure.
- `ruff`, `ruff format --check`, `mypy apps config scripts` (strict): clean; `makemigrations --check`: no changes (blacklist migrations come from SimpleJWT).
- Not yet covered end to end (needs the P2-09 views): login/refresh/logout responses setting and clearing cookies, `no_store` on them, CSRF cookie issued at login.

## P2-09
- `pytest -q` (real PostgreSQL + Redis): 868 passed, 0 skipped, coverage 100 % (1761 statements). New: `test_auth_login.py` (24), `test_auth_session.py` (21), `test_auth_enrollment.py` (17), `test_auth_input.py` (58); helper `tests/accounts/helpers.py`; `tests/testapp/urls_with_auth.py` (real auth routes next to the test app's `whoami`); `timing` and `security` pytest markers registered.
- Login: cookies + CSRF cookie + minimal body + `no-store`; MFA required / replay refused / next step accepted; code not burned by a wrong password; six different failure kinds produce byte-identical 401s; each failure path performs exactly one password verification (call-count spy); Argon2 median ratio unknown-user vs wrong-password within 0.5x-2x; hash upgrade keeps epoch and `password_changed_at`; case-insensitive email; fullwidth look-alike not matched; tokens in body only in body mode; throttle -> 429 with `Retry-After` and `{code: throttled}`, throttled requests never reach the hash; no password, code or cookie value in DEBUG logs; failed audit write -> 500, no cookies, no outstanding token.
- Refresh/logout: rotation chain; missing CSRF -> 403 **and the token is not rotated**; no/garbage/expired/access-typed cookie -> 401 with cookies cleared; replay of a rotated token over HTTP -> identical 401 (no hint of theft), epoch bumped, audit event, victim's access and newest refresh dead; body-mode refresh without CSRF, and ignored when the mode is off; unknown body fields not echoed; logout needs auth and CSRF, blacklists and clears (attributes mirrored), is idempotent (3 calls: 1 blacklist row, 3 audit events), ignores garbage and **other users'** refresh cookies, leaves other sessions alone; failed audit write rolls the logout back.
- Enrolment over HTTP: Admin and Campaign Manager get the restricted credential and no cookies; wrong password gets none; Sales gets a normal session; full flow ends in a session, then a code is required and the enrolment code cannot be replayed; the credential dies at confirmation; begin twice replaces the pending device; 409 paths; session users and garbage headers get 401 + `WWW-Authenticate: MfaEnroll`; the credential is useless on `/whoami/`, `/things/`, `/retry-policy/` even where Bearer is honoured; shares the login throttle; no secret, token or code in logs or audit.
- Hostile input: 17 malformed credential bodies (numeric password, null, list, object, bool, over-length, blank) -> identical generic 400; unknown fields (incl. `__proto__`) not echoed; non-object and invalid JSON; form/multipart/text/xml -> 415; 16 KiB body -> 413; 8 000-level arrays and 1 100-level objects -> 400; NUL bytes -> 400; emoji, RTL override, Turkish dotted I, SQL-injection text, 244-character emails -> 400/401; lone surrogates sent as JSON escapes -> 400/401; wrong methods -> 405/401 with the standard shape; no traceback, SQL or settings text in errors; recursion error simulated -> 400.
- Mutation spot-checks (protection removed -> named tests fail; caches cleared; sources restored; full suite 868 passed):
  1. unknown user skips the dummy hash -> `..._exactly_one_password_verification[unknown_user]`, Argon2 timing test FAILED.
  2. distinct response for inactive users -> `test_every_failure_is_the_same_response` FAILED.
  3. refresh skips CSRF -> `test_refresh_without_the_csrf_header_is_403_and_does_not_rotate` FAILED.
  4. hash upgrade via `save()` -> `test_hash_upgrade_does_not_sign_the_user_out` FAILED.
  5. logout revokes any token -> `test_logout_never_revokes_someone_elses_refresh_token` FAILED.
  6. body limit removed -> `test_oversized_bodies_are_413_...` FAILED.
  7. responses cacheable -> 9 tests FAILED. 8. audit label stores any text -> `test_a_password_typed_into_the_email_field_is_never_stored` FAILED. 9. unknown fields accepted -> 7 tests FAILED.
- Process notes, stated plainly: (a) my first attempt to remove a skipped test half-applied and left a failing baseline, which the first mutation run exposed (the same test failed under every mutation); fixed and the baseline re-verified before counting results; (b) mutation 8 initially did not apply because ruff had re-wrapped the target line (assertion in the harness) and was redone; (c) the throttle caught several of my own tests (6 logins in a loop, login+refresh sharing a bucket): that is the design working.
- `ruff`, `ruff format --check`, `mypy apps config scripts` (strict): clean.
- Not yet done (P2-10/P2-14): axes lockout and trusted-proxy client IP; OpenAPI annotations and the blocking contract check for these three paths.

## R1 Baseline (re-run this session, clean clone of origin/phase-2/identity-security at 1cfa71a, then fix 6d32d34)
| Check | Command | Result |
|---|---|---|
| Branch / tree | `git status -sb`, `git log --oneline origin/main..HEAD` | clean, in sync with origin, 21 commits ahead of main |
| Services | `apt install postgresql redis-server`, `psql select version()`, `redis-server --version` | PostgreSQL 16.15, Redis 7.0.15 |
| Install | `pip install --require-hashes -r backend/requirements/dev.txt` (fresh venv, Python 3.12.3) | success; Django 5.2.17, PyJWT 2.15.0, axes 8.3.1, pyotp 2.10.0 |
| Lint / format | `ruff check .`, `ruff format --check .` | pass; 104 files formatted |
| Types | `mypy apps config` | no issues in 57 source files |
| Tests | `pytest -q --cov` | before fix 868 passed, 100% (1761 stmts); after fix 874 passed, 100% (1791 stmts) |
| Migrations | `makemigrations --check --dry-run` | No changes detected |
| Deploy check | `check --deploy --fail-level WARNING` (prod, throwaway env) | BEFORE: exit 1, 9 issues (3x drf_spectacular.W001, 6x W002). AFTER: "no issues", exit 0 |
| Bandit | `bandit -q -r apps config -ll` | no findings |
| pip-audit | `pip-audit -r requirements/prod.txt -r requirements/dev.txt --require-hashes` | No known vulnerabilities found |
| gitleaks | v8.21.2 with `.gitleaks.toml`, full history (55 commits) and `origin/main..HEAD` (23) | no leaks found |
| Contract | `scripts/check_api_contract.py` | BEFORE: drift on all 3 paths (missing 204/401/429) + 3 additions. AFTER: only the 3 additions (informational after P2-14) |

Deliverable confirmation (files + tests exist): P2-04 roles/registry/sync_roles/matrix drift (tests/accounts/test_roles_matrix.py, test_sync_roles.py); P2-05 HasCapability, scoping, default-deny, `is_superuser` ignored (test_permissions.py, test_scoping*.py, tests/test_default_deny.py; permissions.py never reads `is_superuser`); P2-06 audit model/trigger/rollback/redaction (tests/audit/*); P2-07 MFA seeds encrypted, replay, restricted credential (test_mfa*.py); P2-08 type confusion (`test_a_refresh_token_is_not_an_access_token_and_vice_versa`), epoch, reuse, CSRF, no-store (test_tokens.py, test_cookie_auth.py). P2-02 Phase 1 edits (ENV-VARIABLES.md, tests/conftest.py, tests/config/test_settings.py, gen_throwaway_env.py) are recorded in DECISIONS.md. `git diff origin/main...HEAD -- docs/phase-0 spike "ai_calling agent"` is empty; the only docs/phase-1 change is ENV-VARIABLES.md.
Not verified here: pre-commit hook environments, Docker, GitHub-hosted CI (unchanged).
Environment note: the sandbox PostgreSQL/Redis stopped between tool calls once; restart with `service postgresql start; redis-server --daemonize yes`. A run during the outage produced 504 errors that were environmental, not code (re-run after restart: all green).

## R2 Global error handler (OQ2-20)
- `pytest -q --cov`: 897 passed (874 before), coverage 100% (1839 stmts, 0 missed). `ruff check`, `ruff format --check`, `mypy apps config` (59 files): clean.
- New `tests/core/test_error_contract.py`: one test per exception class (validation, parse, authentication-failed, not-authenticated, permission-denied, Django PermissionDenied, Http404, NotFound, MethodNotAllowed, NotAcceptable, UnsupportedMediaType, Throttled with `Retry-After: 30`, an unlisted APIException (418), unhandled RuntimeError), the Django-level 400 (SuspiciousOperation and DisallowedHost), 403, 404 (routed and unrouted), 500 and the CSRF failure view. Every response is validated against the contract's `Error` schema loaded from `API-Specification.yaml` with `jsonschema` (Draft 7), has exactly the keys `code` and `message`, carries `X-Request-ID`, and never contains the planted SQL/secret text. A DEBUG=False test asserts no `Traceback`, `SELECT`, `SECRET_KEY`, `settings`, `RuntimeError` or file path appears.
- Mutation 1: replaced the handler's body rewrite with `pass` -> 58 failed (tests/core + tests/accounts); restored. Mutation 2: removed `handler404` from `config/urls.py` -> only a collection error (the test urlconf imports the handler by name), i.e. a weak signal; the Django-level 404 is also asserted by `test_unrouted_path_is_a_json_404`. Restored; `tests/core` 157 passed after restore.
- Test bug found and fixed on the way: DRF sets `status_code = 403` on the exception *instance* when a view offers no auth challenge, so shared module-level exception instances poisoned later requests (order-dependent failures). The test urlconf now builds a fresh exception per request.
- `check --deploy --fail-level WARNING` prod and staging: no issues. `bandit -ll`: clean. `grep '"detail"' apps config`: no matches. Contract script: only the three proposed additions drift (P2-14 reclassifies them).

## R6 Absolute session cap (branch phase-2/s1-session-me-logout)
- Full gate: `pytest -q --cov` 929 passed, coverage 100% (1875 stmts, 0 missed); `ruff check`, `ruff format --check`, `mypy apps config` (59 files) clean; `check --deploy --fail-level WARNING` exit 0 for prod and staging; `bandit -ll` exit 0.
- New tests: `tests/accounts/test_session_cap.py` (21): `sid`/`sat` issued and equal in both tokens; two logins = two sessions; rotation preserves `sid`/`sat`; refresh at cap-1 s succeeds after a chain of 13 rotations, at cap+1 s is rejected although the refresh token is valid; one audit event per rejection and no epoch bump; replay of an expired token is not treated as reuse; deleted-user branch; access token past the cap rejected (and cap-60 s accepted); missing/malformed claims (7 cases); tampering with `sat`/`sid` breaks the signature (wrong key and edited payload segment); type confusion still rejected. HTTP: `test_refresh_past_the_absolute_cap_is_the_uniform_401_even_for_an_active_session` (24 rotations over 7 days, then 401 with cleared cookies and the uniform body). Settings: prod requires the variable, bounds 1-90, rejects a cap shorter than the refresh lifetime, accepts equal.
- Mutations (all applied, `grep -c MUTATION` = 1 each; baseline restored and re-verified at 541 passed in `tests/accounts` before counting): M1 `session_expired()` always False -> 5 failed; M2 rotation resets `sat` (activity extends the session) -> 5 failed; M3 `read_access` ignores the cap -> 1 failed (so that single test is the only guard of the access-token check).
- Test-authoring notes: a first version of two tests ticked a straight 7 days, which expires the 1-day refresh token before the cap; the cap only matters for a chain kept alive by rotation, so tests now build that chain. An off-by-milliseconds boundary in the HTTP test (login happened just before the clock froze) was fixed by testing 5 s either side of the cap.

## R3 GET /auth/me
- Full gate: `pytest -q --cov` 963 passed, 100% (1911 stmts, 0 missed); ruff, `ruff format --check`, `mypy apps config` clean; `check --deploy --fail-level WARNING` exit 0 (prod, staging); `bandit -ll` exit 0; contract script lists `/auth/me` only as a proposed addition (reclassified in P2-14).
- `tests/accounts/test_me.py` (34): exact key set (top level, `mfa`, `session`); `no-store`; capabilities of each of the 4 roles equal the RBAC registry (`ROLE_CAPABILITIES`); per-user grant appears; `is_superuser` adds nothing; no-role user; MFA state matrix (4 cases + unconfirmed device); `access_expires_at` = login + access lifetime and `absolute_expires_at` = login + cap under frozen time, and the latter does not move after rotation; anonymous / deactivated / epoch bumped / deleted / expired / bad cookies (3) / refresh token in the access cookie -> uniform 401; restricted enrolment credential -> 403 and the email is not in the body; invalid enrolment credential -> 401; non-human principals and a credential without the `restricted` flag refused by the permission; write methods refused; `api-user` throttle (429 with `Retry-After`, per-user buckets, login scope untouched); no audit event; log line has `user_id` and no email or name.
- Mutations (all applied, baseline restored and re-verified at 34 passed): restricted flag ignored -> 2 failed; non-`User` principals accepted -> 3 failed; `is_superuser` capability shortcut -> 1 failed; throttle removed -> 2 failed; `no-store` dropped -> 2 failed.

