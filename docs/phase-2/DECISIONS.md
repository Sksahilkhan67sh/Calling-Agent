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
