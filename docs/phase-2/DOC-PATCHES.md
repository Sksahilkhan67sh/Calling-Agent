# Phase 2 — Proposed doc patches

_Populated by the task that owns it (see PROGRESS.md)._

## From P2-07 (proposed spec additions, to be finalised with the endpoints in P2-09/P2-14)
- **MFA enrolment credential.** `POST /auth/token` for a user who must enrol returns 200 with `{"mfa_enrollment_required": true, "mfa_enrollment_token": "<token>", "expires_in": 600}` and **no session cookies**. The two enrolment endpoints (`POST /auth/mfa/enroll`, `POST /auth/mfa/confirm`) are secured by a new security scheme: `Authorization: MfaEnroll <token>` (`http`, custom scheme). The token is valid only for those two endpoints.
- **Security schemes** to define in the spec: cookie auth (access cookie + `X-CSRFToken`), `ApiKey`, and `MfaEnroll`.
