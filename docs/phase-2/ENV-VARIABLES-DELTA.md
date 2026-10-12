# Phase 2 — environment variable delta

The authoritative table is `docs/phase-1/ENV-VARIABLES.md` (the drift test reads it). This file lists what Phase 2 changed.
No secret values appear here or in any test: tests generate throwaway values at runtime.

## New variables
`JWT_ACCESS_LIFETIME_SECONDS`, `JWT_REFRESH_LIFETIME_SECONDS`, `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_DOMAIN`, `AUTH_TOKENS_IN_BODY`,
`CSRF_TRUSTED_ORIGINS`, `AXES_FAILURE_LIMIT`, `AXES_COOLOFF_MINUTES`, `TRUSTED_PROXY_COUNT`, `MFA_REQUIRED_ROLES`, `MFA_ISSUER_NAME`,
`MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS`, `API_CLIENT_LAST_USED_WRITE_INTERVAL_SECONDS`.

## Variables whose rules tightened (production/staging only; dev and test keep defaults)
| Variable | Phase 1 | Phase 2 |
|---|---|---|
| `JWT_SIGNING_KEY` | ≥ 32 chars | ≥ 50 chars |
| `CORS_ALLOWED_ORIGINS` | optional, default empty | required, non-empty, `https://` only (credentialed CORS) |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | optional, default 5 | required |
| `AXES_FAILURE_LIMIT`, `TRUSTED_PROXY_COUNT`, `CSRF_TRUSTED_ORIGINS` | n/a | required, no default |

Deployment impact: existing prod/staging environments must set these five variables before deploying Phase 2.

## Fixed in code, deliberately not environment variables
JWT algorithm (HS256), issuer, audience; auth cookie names; TOTP algorithm (SHA-1), digits (6), period (30 s), window (±1 step); API version prefix (`v1`).
A deployment must not be able to weaken them. Each is asserted by `tests/config/test_settings_auth.py`.

## Rate values (Threat Model risk #6)
Phase 1 OQ-01 stays open: `API_RATE_LIMIT_PER_MINUTE`, `WEBHOOK_RATE_LIMIT_PER_MINUTE` and `LOGIN_RATE_LIMIT_PER_MINUTE` in prod must come from load-test results
(Environment-Config §4). Whoever sets them records the source run and date next to the deployment config.
