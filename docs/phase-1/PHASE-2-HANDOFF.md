# Phase 2 handoff (authentication and RBAC)

## What exists
| Module | API |
|---|---|
| `core.settings_utils` | `required`, `optional`, `as_int`, `as_bool`, `as_list`, `as_csv_hosts`, `reject_placeholder`; every read is registered and must be documented in `ENV-VARIABLES.md` (test-enforced) |
| `core.crypto` | `FieldCipher(keys).encrypt/decrypt(text, context=...)`, `needs_rotation`, `parse_encryption_keys`, `parse_hmac_key`, `blind_index(value, key=, purpose=)` |
| `core.logging` | `bind_context`, `context(...)`, `get_context`, `clear_context`, `redact_text/redact_value`, `RedactionFilter`, `JsonFormatter`, `build_logging_config` |
| `core.middleware` | `RequestContextMiddleware` (first in `MIDDLEWARE`) |
| `core.permissions` | `DefaultDeny` (DRF default), `PublicEndpoint` (explicit anonymous, reviewed allowlist only) |
| `core.throttles` | `LoginThrottle`, `ApiUserThrottle` (default), `ApiClientThrottle`, `WebhookThrottle` |
| `core.health` | `/healthz`, `/readyz` |
| `accounts.User` | UUID pk, email login, ci-unique email, Argon2 hashing, no roles |

## Conventions to follow
UUID primary keys; `timestamptz` (`USE_TZ=True`); bind correlation ids with `context(...)` and pass `log_context` to Celery tasks;
every DRF view declares `permission_classes` (the walker test fails otherwise; add any new anonymous view to the reviewed allowlist only after review);
read configuration only through `settings_utils` and document every new variable in `ENV-VARIABLES.md`; migrations additive and backward-compatible;
encrypted columns use `FieldCipher` with a `table.column` context; never log secrets (the filter is a safety net, not permission);
tests: unit tests must run without services, mark service-dependent ones `@pytest.mark.integration`; keep 90 %+ coverage on `core` and `config`.

## Extension points for Phase 2
- `AUTH_USER_MODEL = "accounts.User"` (add roles/MFA fields with additive migrations; the `email` normalisation and `lower(email)` constraint stay).
- `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]` is **empty on purpose**: Phase 2 adds JWT authentication; views then replace `DefaultDeny` with real permissions.
- Throttle scopes `login`, `api-user`, `api-client` exist; `ApiUserThrottle` already keys on the authenticated user id.
- `JWT_SIGNING_KEY` is already a required, validated variable (≠ `DJANGO_SECRET_KEY`).
- Sessions, `AuthenticationMiddleware` and the admin are not installed; add only if needed (the design uses JWT cookies, so CSRF protection stays on).
- `tests/test_default_deny.py` allowlist and `scripts/check_api_contract.py` (`/auth/token`, `/auth/token/refresh` are the contract's only unauthenticated paths) should be updated as the auth endpoints land.

## Decisions Phase 2 must make
JWT cookie strategy (httpOnly cookies vs bearer, refresh rotation, CSRF double-submit); MFA library; django-axes configuration and its interaction with `LoginThrottle` (OQ-04);
RBAC model (roles named in Security Architecture §2); how the contract check turns "not yet implemented" into a failure for the auth paths.
