"""Redaction and bounding of audit payloads (before/after/metadata).

Reuses the Phase 1 log redaction (secret-shaped keys and values, tokens, artifact URLs, phone numbers)
and adds the authentication field names, so a secret can never reach the audit table even if a caller
passes a whole serializer or model dict by mistake.
"""

from __future__ import annotations

import json
from typing import Any

from apps.core.logging import REDACTED, redact_value

MAX_PAYLOAD_BYTES = 16 * 1024
# Matched exactly (after lower-casing and "-" -> "_"), in addition to the Phase 1 key rules.
AUDIT_SENSITIVE_KEYS = frozenset(
    {
        "otp",
        "code",
        "totp",
        "seed",
        "secret_encrypted",
        "sessionid",
        "csrftoken",
        "provisioning_uri",
        "otpauth",
        "access_cookie",
        "refresh_cookie",
        "__host_access",
        "__secure_refresh",
        "x_api_key",
        "key",
        "key_hash",
    }
)


def redact_payload(value: Any) -> Any:
    """Return a JSON-safe, redacted, size-bounded copy of ``value`` (``None`` stays ``None``)."""
    if value is None:
        return None
    cleaned = redact_value(value, extra_keys=AUDIT_SENSITIVE_KEYS)
    size = len(json.dumps(cleaned, default=str, separators=(",", ":")).encode())
    if size > MAX_PAYLOAD_BYTES:
        return {"_truncated": True, "_original_bytes": size}
    return cleaned


__all__ = ["AUDIT_SENSITIVE_KEYS", "MAX_PAYLOAD_BYTES", "REDACTED", "redact_payload"]
