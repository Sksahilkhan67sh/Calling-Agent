# Phase 2 — Decisions

_Populated by the task that owns it (see PROGRESS.md)._

## P2-01 Dependencies (release dates checked on PyPI, 2026-10-12)
| Package | Pin | Released | Why |
|---|---|---|---|
| djangorestframework-simplejwt | 5.5.1 | 2025-07-21 | Latest stable; declares Django 5.2 support |
| django-axes | 8.3.1 | 2026-02-11 | Latest stable; declares Django 5.2 support |
| pyotp | 2.10.0 | 2026-06-14 | Latest stable (RFC 6238 TOTP); chosen over django-otp, which stores TOTP keys in plaintext |
| pyjwt (transitive of simplejwt, pinned explicitly) | 2.15.0 | 2026-09-23 | 2.14.0 has PYSEC-2026-4141/4183 (fixed in 2.15.0); 2.15.1 (2026-09-28) is inside the 14-day cooling-off window, 2.15.0 is outside it |

`django-otp` and `allauth` deliberately not added. No other pin changed (verified by diffing pin sets of base/prod/dev against Phase 1).
The lock headers no longer reference `/tmp/constraints.txt` (regenerated with the repo's `make lock` command form); hash counts per package are unchanged.

## P2-02 Settings and environment
- **Fixed in code, not env:** JWT algorithm HS256, issuer, audience, cookie names, TOTP parameters, API prefix `v1`. A deployment must not be able to weaken them; tests assert an env `JWT_ALGORITHM=none` is ignored. HS256 because one service signs and verifies, so there is no key distribution problem; the signing key is separate from `DJANGO_SECRET_KEY` and ≥ 50 chars in prod (spec value; Phase 1 had 32).
- **Refresh lifetime default 24 h (`JWT_REFRESH_LIFETIME_SECONDS`, bounds 1 h–30 d).** Tokens rotate on every use, so this is an *idle* timeout: a dashboard unused for a day re-authenticates with password + MFA. Rejected: 7–30 days (long theft window; reuse detection only fires if the thief and the user both use the token). No absolute session cap in Phase 2 (see OPEN-QUESTIONS).
- **SameSite=Lax (`COOKIE_SAMESITE` input).** Lax keeps top-level navigation working and still blocks cross-site POST/XHR cookies; Strict would drop the session on every inbound link. Requirement this creates: dashboard and API must be **same-site** (same registrable domain, e.g. `dashboard.x.com` and `api.x.com`). `SameSite=None` is refused by settings. If the dashboard lands on a different registrable domain, this decision must be revisited together with CSRF.
- **Cookie names:** `__Host-access` and `__Host-csrftoken` (Secure, Path=/, no Domain); refresh is `__Secure-refresh` because it is path-scoped to `/v1/auth/`, which `__Host-` forbids. Setting `AUTH_COOKIE_DOMAIN` downgrades access/CSRF to `__Secure-`. Dev (plain HTTP) uses unprefixed names because browsers reject prefixed cookies without Secure.
- **CSRF cookie is not HttpOnly** (double-submit: the SPA must read it). The auth cookies are HttpOnly.
- **Credentialed CORS** (`CORS_ALLOW_CREDENTIALS=True`) is always on in settings but prod refuses to start unless `CORS_ALLOWED_ORIGINS` is a non-empty explicit list of `https://` origins (also applied to `CSRF_TRUSTED_ORIGINS`). `as_origins` rejects wildcards, paths, trailing slashes and non-http(s) schemes.
- **`TRUSTED_PROXY_COUNT`, `AXES_FAILURE_LIMIT`, `LOGIN_RATE_LIMIT_PER_MINUTE` have no prod default.** Wrong values here either disable lockout/rate limiting or let a client forge its address. `LOGIN_RATE_LIMIT_PER_MINUTE` was optional in Phase 1; this is a deliberate tightening (deployment impact listed in ENV-VARIABLES-DELTA.md).
- **TOTP SHA-1 / 6 digits / 30 s / ±1 step.** Google Authenticator and most apps ignore the `algorithm` URI parameter and always use SHA-1; choosing SHA-256 would silently break enrolment for those apps. RFC 6238 permits SHA-1; the secret is 160 bits and replay is blocked (P2-07).
- **`MFA_REQUIRED_ROLES`** is validated against the known role names (a typo such as "Campaign Manger" would silently exempt a role) and prod requires both Admin and Campaign Manager. Role names live in `apps/accounts/roles.py` (pure constants) so settings and later code share one source.
- **Axes settings are defined here; `axes` is installed and wired in P2-10** (it adds migrations and a middleware/backend, which belong with the lockout tests). `AXES_LOCKOUT_PARAMETERS=[["username","ip_address"]]` locks one account from one address only; the axes semantics are re-verified against the installed version in P2-10.
- **Phase 1 files touched by this task (necessary consequences, no behaviour removed):** `docs/phase-1/ENV-VARIABLES.md` (the drift test reads it, and P2-02 explicitly asks for it), `tests/conftest.py` and `tests/config/test_settings.py` (new required prod variables, JWT key length), `scripts/gen_throwaway_env.py` (CI deploy check needs the new variables).

## P2-03 User model extension
- **Fields (additive migration `0002_user_epoch_and_profile`):** `full_name`, `auth_epoch`, `password_changed_at`. `first_name`/`last_name` from `AbstractUser` stay (dropping them would not be additive) and are unused. Email remains the identity (case-insensitive unique from Phase 1).
- **`db_default` as well as `default`.** Django's plain `default` drops the column default after `ADD COLUMN`, which would make an older app version inserting a user during a rolling deploy fail on NOT NULL. With `db_default` the SQL keeps `DEFAULT 0` / `DEFAULT ''` (checked with `sqlmigrate`); a test inserts a row the way old code would. The migration reverses cleanly (`sqlmigrate --backwards`).
- **Epoch is monotonic by construction.** Only `bump_auth_epoch()` changes it, as an atomic `UPDATE … SET auth_epoch = auth_epoch + 1`. `save()` never writes the column (it passes an explicit `update_fields` without it) and `update_fields=["auth_epoch"]` raises. Rejected: `self.auth_epoch += 1; save()`, because a stale in-memory copy would overwrite a higher value and revive revoked tokens. The column has a DB `CHECK (auth_epoch >= 0)` from `PositiveIntegerField`.
- **Password change and deactivation revoke automatically inside `save()`**, detected by comparing with the row locked in the same transaction (`SELECT … FOR UPDATE`). Rejected: relying on callers (management commands, future endpoints) to remember. Cost: one extra indexed SELECT per *update* of a user (rare: no `last_login` write, no per-request saves). Reactivation does not bump (tokens died at deactivation). Bypasses: `QuerySet.update()`/`bulk_update()` skip `save()`; no Phase 2 code uses them on `User` and P2-11 adds a test that the commands go through `save()`.
- **Role changes (group membership)** are M2M, not `save()`: the `m2m_changed` hook that bumps the epoch is part of P2-11.
- **Saving a user whose row no longer exists raises `DoesNotExist`.** Django's default would re-insert it with its old epoch and password, un-revoking it.
- **`requires_mfa` is computed from group names and `MFA_REQUIRED_ROLES`.** The spec's `must_enroll_mfa` (requires MFA and has no confirmed device) needs `MfaDevice`; P2-07 adds it on top of this property.
- **Superusers.** Django's `is_superuser` makes `has_perm` return True for everything. Phase 2 users are never created as superusers (P2-13 commands set only groups) and `HasCapability` (P2-05) must evaluate capabilities from role membership **without** honouring `is_superuser`, so the flag cannot bypass RBAC.
- **Password validators** were already on (min 12, common, numeric, similarity). The similarity validator now compares against `email` and `full_name` (there is no username).
- **Tooling:** mypy is now strict on `apps.accounts.*` (migrations excluded); coverage now includes `apps/accounts` (migrations omitted).
