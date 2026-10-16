"""Registry of API error codes: the single source of every ``{code, message}`` pair the API emits.

The contract's ``Error`` schema (API-Specification.yaml) is ``{code: string, message: string}``. Codes are
stable and machine readable; messages are generic on purpose and never carry request data, field names or
internals. Mapping is by HTTP status so no exception class can accidentally choose its own wording.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    status: int

    def body(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


INVALID_REQUEST = ApiError("invalid_request", "Invalid request.", 400)
INVALID_CREDENTIALS = ApiError("invalid_credentials", "Invalid credentials.", 401)
FORBIDDEN = ApiError("forbidden", "The request was rejected.", 403)
CSRF_FAILED = ApiError("csrf_failed", "The request was rejected.", 403)
NOT_FOUND = ApiError("not_found", "Not found.", 404)
METHOD_NOT_ALLOWED = ApiError("method_not_allowed", "Method not allowed.", 405)
NOT_ACCEPTABLE = ApiError("not_acceptable", "Not acceptable.", 406)
PAYLOAD_TOO_LARGE = ApiError("payload_too_large", "Request body too large.", 413)
UNSUPPORTED_MEDIA_TYPE = ApiError("unsupported_media_type", "Content type must be application/json.", 415)
THROTTLED = ApiError("throttled", "Too many requests.", 429)
INTERNAL_ERROR = ApiError("internal_error", "Internal server error.", 500)
REQUEST_FAILED = ApiError("error", "Request failed.", 0)  # fallback for a status with no entry

# Endpoint-specific codes (still generic text).
ENROLLMENT_UNAVAILABLE = ApiError("enrollment_unavailable", "Enrolment is not available.", 409)
NO_ENROLLMENT = ApiError("no_enrollment", "No enrolment is in progress.", 409)
INVALID_CODE = ApiError("invalid_code", "The code is not valid.", 400)

BY_STATUS: dict[int, ApiError] = {
    e.status: e
    for e in (
        INVALID_REQUEST,
        INVALID_CREDENTIALS,
        FORBIDDEN,
        NOT_FOUND,
        METHOD_NOT_ALLOWED,
        NOT_ACCEPTABLE,
        PAYLOAD_TOO_LARGE,
        UNSUPPORTED_MEDIA_TYPE,
        THROTTLED,
        INTERNAL_ERROR,
    )
}

ALL: tuple[ApiError, ...] = (
    *BY_STATUS.values(),
    CSRF_FAILED,
    REQUEST_FAILED,
    ENROLLMENT_UNAVAILABLE,
    NO_ENROLLMENT,
    INVALID_CODE,
)


def for_status(status: int) -> ApiError:
    """The registry entry for ``status``; an unlisted status gets the generic fallback."""
    return BY_STATUS.get(status, REQUEST_FAILED)
