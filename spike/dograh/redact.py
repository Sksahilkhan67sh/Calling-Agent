"""Redaction helpers: everything that is saved as evidence passes through here first."""
import json
import os
import re
from urllib.parse import urlsplit

MASK = "***"
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}
SENSITIVE_KEYS = {"token", "secret", "api_key", "apikey", "password", "authorization",
                  "public_access_token", "signature"}
E164 = re.compile(r"\+\d{6,15}")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
URL = re.compile(r"https?://[^\s\"'<>]+")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def mask_phone(number: str) -> str:
    """Keep the country code and the last two digits. One-digit codes: +1 and +7; others are
    treated as two digits, so a three-digit code (for example +971) leaks one national digit."""
    digits = number.lstrip("+")
    cc = 1 if digits[0] in "17" else 2
    if len(digits) <= cc + 2:
        return "+" + MASK
    return f"+{digits[:cc]}{'*' * (len(digits) - cc - 2)}{digits[-2:]}"


def _segment(seg: str) -> str:
    return "<token>" if UUID.match(seg) or len(seg) >= 24 else seg


def redact_url(url: str) -> str:
    """Keep scheme, host and path; drop query/fragment; hide token-looking path segments."""
    parts = urlsplit(url)
    path = "/".join(_segment(s) for s in parts.path.split("/"))
    return f"{parts.scheme}://{parts.netloc}{path}"


def redact_text(text: str) -> str:
    text = JWT.sub(MASK, text)
    text = URL.sub(lambda m: redact_url(m.group(0)), text)
    return E164.sub(lambda m: mask_phone(m.group(0)), text)


def header_shape(value: str) -> str:
    """Describe a secret value without revealing it, e.g. 'len=43 chars=base64url'."""
    if re.fullmatch(r"[0-9a-fA-F]+", value):
        kind = "hex"
    elif re.fullmatch(r"[A-Za-z0-9_-]+", value):
        kind = "base64url"
    else:
        kind = "mixed"
    return f"len={len(value)} chars={kind}"


def redact_headers(headers: dict, extra_secret_headers: tuple = ()) -> dict:
    secret = SENSITIVE_HEADERS | {h.lower() for h in extra_secret_headers if h}
    configured = os.environ.get("DOGRAH_WEBHOOK_HEADER_NAME", "").lower()
    if configured:
        secret.add(configured)
    return {k: (f"{MASK} ({header_shape(v)})" if k.lower() in secret else redact_text(v))
            for k, v in headers.items()}


def redact_obj(obj):
    if isinstance(obj, dict):
        return {k: (MASK if k.lower() in SENSITIVE_KEYS else redact_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def redact_body(raw: bytes) -> str:
    """Redact a raw request/response body; JSON is parsed so key-based masking applies."""
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.dumps(redact_obj(json.loads(text)), indent=2, sort_keys=True)
    except ValueError:
        return redact_text(text)
