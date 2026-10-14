# Phase 2 — Proposed doc patches

_Populated by the task that owns it (see PROGRESS.md)._

## From P2-07 (proposed spec additions, to be finalised with the endpoints in P2-09/P2-14)
- **MFA enrolment credential.** `POST /auth/token` for a user who must enrol returns 200 with `{"mfa_enrollment_required": true, "mfa_enrollment_token": "<token>", "expires_in": 600}` and **no session cookies**. The two enrolment endpoints (`POST /auth/mfa/enroll`, `POST /auth/mfa/confirm`) are secured by a new security scheme: `Authorization: MfaEnroll <token>` (`http`, custom scheme). The token is valid only for those two endpoints.
- **Security schemes** to define in the spec: cookie auth (access cookie + `X-CSRFToken`), `ApiKey`, and `MfaEnroll`.

## From P2-09 (proposed spec additions; the contract script check in P2-14 treats the three contract paths as blocking)
- `POST /auth/token`: add `400` (malformed request, generic), `413`, `415`; 200 body `{authenticated, mfa_enrollment_required}` (+ `mfa_enrollment_token`, `expires_in` in enrolment state, + `access`/`refresh` only when tokens-in-body mode is on); `Set-Cookie` for access, refresh and CSRF cookies; `Retry-After` on 429; every response `Cache-Control: no-store`. State that every credential failure is the same 401.
- `POST /auth/token/refresh`: add `403` (CSRF failure for the cookie credential) and the `X-CSRFToken` header requirement; `429`; optional body `{refresh}` in tokens-in-body mode; 401 clears cookies.
- `POST /auth/logout`: requires the CSRF header with cookie authentication; add `401`, `403`.
- New: `GET /auth/csrf` (204, sets the CSRF cookie), `POST /auth/mfa/enroll`, `POST /auth/mfa/confirm` secured by a new `MfaEnroll` HTTP scheme (see P2-07 entry).
- Document the cookie names and flags (`__Host-access`, `__Secure-refresh`, CSRF cookie readable by the SPA) in the security scheme descriptions.
