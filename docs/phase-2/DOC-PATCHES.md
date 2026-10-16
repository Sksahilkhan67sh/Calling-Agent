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

## R2 Error responses (API-Specification.yaml)
- Every `4xx/5xx` response in the contract should reference `#/components/schemas/Error`; today only some do. Add the standard responses `BadRequest 400`, `Forbidden 403`, `NotFound 404`, `TooManyRequests 429` (with `Retry-After` header) and `ServerError 500` under `components/responses` and reference them.
- Proposed text for field-level validation (the contract has none, so none was invented): either keep `Error` as is and accept non-specific 400s, or extend it compatibly with an optional `fields: {name: [code]}` map of stable codes (never values). Phase 2 emits only `{code, message}` until the human decides.
- Document the code registry (`apps/core/error_codes.py`) as the enumeration for `Error.code`:
```yaml
Error:
  type: object
  required: [code, message]
  properties:
    code:    {type: string, enum: [invalid_request, invalid_credentials, forbidden, csrf_failed, not_found, method_not_allowed, not_acceptable, payload_too_large, unsupported_media_type, throttled, internal_error, enrollment_unavailable, no_enrollment, invalid_code]}
    message: {type: string}
```

## R3 `GET /auth/me` (addition to API-Specification.yaml)
```yaml
  /auth/me:
    get:
      tags: [Auth]
      summary: The signed-in user, their roles, effective capabilities, MFA state and session expiry
      security:
        - cookieAuth: []
      responses:
        '200':
          description: Current user (Cache-Control no-store)
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Me'}
        '401': {$ref: '#/components/responses/Unauthorized'}   # Error {code: invalid_credentials}
        '403': {$ref: '#/components/responses/Forbidden'}      # API client or MFA-enrolment credential
        '429': {$ref: '#/components/responses/TooManyRequests'}
components:
  schemas:
    Me:
      type: object
      required: [id, email, full_name, roles, capabilities, mfa, session]
      additionalProperties: false
      properties:
        id: {type: string, format: uuid}
        email: {type: string, format: email}
        full_name: {type: string}
        roles: {type: array, items: {type: string}}
        capabilities: {type: array, items: {type: string}, description: Sorted effective set (roles plus per-user grants); is_superuser grants nothing}
        mfa:
          type: object
          required: [required, enrolled]
          properties: {required: {type: boolean}, enrolled: {type: boolean}}
        session:
          type: object
          required: [access_expires_at, absolute_expires_at]
          properties:
            access_expires_at: {type: string, format: date-time}
            absolute_expires_at: {type: string, format: date-time, description: End of the absolute session cap; never extended by refresh}
  securitySchemes:
    cookieAuth: {type: apiKey, in: cookie, name: <access cookie name; __Host- prefix in production>}
```

## R4 `POST /auth/logout`
- Proposed text: logout identifies the caller by the access cookie **or**, when that is missing or expired, by the refresh cookie; it is idempotent and answers `204` for any caller (no credentials, expired, invalid, already revoked) with the auth cookies cleared; `403` only when CSRF fails while a cookie is present. Replaying an already-blacklisted refresh token revokes every session of its owner (same as `/auth/token/refresh`), still answering `204`.
```yaml
  /auth/logout:
    post:
      tags: [Auth]
      summary: End the current session and clear cookies (idempotent)
      security: [{cookieAuth: []}, {}]      # also usable with only the refresh cookie, or with no credentials
      responses:
        '204': {description: Logged out (or nothing to log out); auth cookies cleared}
        '403': {$ref: '#/components/responses/Forbidden'}   # CSRF header missing or wrong while a cookie is present
```

