"""Structured JSON logging, request/task context and redaction.

Design references: Django-Backend-Design §7, Monitoring §6, Threat Model.

One mechanism everywhere: ``bind_context`` / ``context`` put correlation ids in
``contextvars``; the JSON formatter adds them to every line. The
``RedactionFilter`` is attached to EVERY handler (``build_logging_config``) and
removes secrets, secret-shaped values, URL tokens, recording/transcript URLs and
phone numbers from messages, structured fields and exception text.

Over-redaction is the accepted failure mode: a 10-15 digit number is masked even
when it is not a phone number.

Avoid importing Django here: gunicorn loads this module before Django starts.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import traceback
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "CONTEXT_FIELDS",
    "JsonFormatter",
    "RedactionFilter",
    "bind_context",
    "build_logging_config",
    "clear_context",
    "context",
    "get_context",
    "redact_text",
    "redact_value",
]

REDACTED = "[REDACTED]"
MAX_DEPTH = 8
MAX_CONTEXT_VALUE_LENGTH = 128

# --------------------------------------------------------------------------- context

CONTEXT_FIELDS: tuple[str, ...] = (
    "request_id",
    "trace_id",
    "user_id",  # the authenticated principal's id, never an email or token
    "call_id",
    "attempt_id",
    "contact_id",
    "campaign_id",
    "provider_run_id",
)
_context_var: contextvars.ContextVar[Mapping[str, str] | None] = contextvars.ContextVar(
    "log_context", default=None
)


def get_context() -> dict[str, str]:
    return dict(_context_var.get() or {})


def bind_context(**fields: object) -> contextvars.Token[Mapping[str, str] | None]:
    """Add correlation fields. ``None`` values are skipped; unknown names are rejected."""
    unknown = set(fields) - set(CONTEXT_FIELDS)
    if unknown:
        raise ValueError(f"unknown log context field(s): {', '.join(sorted(unknown))}")
    merged = dict(_context_var.get() or {})
    for name, value in fields.items():
        if value is not None:
            merged[name] = str(value)[:MAX_CONTEXT_VALUE_LENGTH]
    return _context_var.set(merged)


def clear_context() -> None:
    _context_var.set({})


@contextmanager
def context(**fields: object) -> Iterator[None]:
    """Bind fields for the duration of the block, then restore the previous context."""
    token = bind_context(**fields)
    try:
        yield
    finally:
        _context_var.reset(token)


# ------------------------------------------------------------------------- redaction

# Substring match on the normalised key (lower case, "-" -> "_").
_SENSITIVE_KEY_SUBSTRINGS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "jwt",
    "signature",
    "credential",
    "private_key",
)
# Exact match only: a substring match would hide harmless keys such as "accessed_at".
_SENSITIVE_KEYS_EXACT = frozenset({"refresh", "access", "key", "sig", "pwd"})


def _normalise_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _is_sensitive_key(key: str, extra: frozenset[str]) -> bool:
    normalised = _normalise_key(key)
    if normalised in _SENSITIVE_KEYS_EXACT or normalised in extra:
        return True
    return any(part in normalised for part in _SENSITIVE_KEY_SUBSTRINGS)


_KEY_WORDS = (
    r"password|passwd|pwd|secret|token|api[_-]?key|apikey|authorization|signature|jwt|cookie|credential"
)
_PATTERN_KEY_VALUE = re.compile(
    rf"(?P<key>\b[A-Za-z0-9_.-]{{0,40}}(?:{_KEY_WORDS})[A-Za-z0-9_.-]{{0,40}})"
    r"(?P<sep>[\"']?\s{0,3}[=:]\s{0,3})"
    r"(?P<value>\[REDACTED\]|\"[^\"]*\"|'[^']*'|(?:(?:bearer|basic|token)\s+)?[^\s,;&}\])\"']+)",
    re.IGNORECASE,
)
_PATTERN_BEARER = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_PATTERN_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_PATTERN_VENDOR_TOKENS = re.compile(
    r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})"
)
_PATTERN_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY-----.*?(?:-----END [A-Z ]{0,30}PRIVATE KEY-----|\Z)", re.DOTALL
)
_PATTERN_URL_USERINFO = re.compile(
    r"(?P<scheme>\b[A-Za-z][A-Za-z0-9+.-]{1,15}://)(?P<user>[^/\s:@]{0,64}):(?P<password>[^/\s@]{1,256})@"
)
_PATTERN_URL_QUERY = re.compile(
    r"(?P<lead>[?&])(?P<name>token|signature|sig|key|expires|x-amz-[A-Za-z0-9-]{1,40})=(?P<value>[^&\s\"'#]*)",
    re.IGNORECASE,
)
# Recording / transcript / artifact download URLs: keep scheme and host only.
_PATTERN_ARTIFACT_URL = re.compile(
    r"(?P<origin>\bhttps?://[A-Za-z0-9.-]{1,253}(?::\d{1,5})?)"
    r"/(?:[^\s\"'?#/]{0,200}/){0,10}?(?:recordings?|transcripts?|artifacts?)(?:/[^\s\"']{0,500}|\?[^\s\"']{0,500}|\b)",
    re.IGNORECASE,
)
_PATTERN_PHONE = re.compile(r"(?<!\w)(?<!\w-)(?P<number>[+(]?\d(?:[\d\-\s().]{8,18})\d)(?!\w|-\w)")
_PATTERN_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

_TWO_DIGIT_COUNTRY_CODES = frozenset(
    {
        *("20", "27", "30", "31", "32", "33", "34", "36", "39", "40", "41", "43", "44"),
        *("45", "46", "47", "48", "49", "51", "52", "53", "54", "55", "56", "57", "58"),
        *("60", "61", "62", "63", "64", "65", "66", "81", "82", "84", "86", "90", "91"),
        *("92", "93", "94", "95", "98"),
    }
)


def _country_code_length(digits: str) -> int:
    if digits[0] in "17":
        return 1
    return 2 if digits[:2] in _TWO_DIGIT_COUNTRY_CODES else 3


def _mask_phone(match: re.Match[str]) -> str:
    raw = match.group("number")
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 15 or _PATTERN_ISO_DATE.match(raw):
        return raw
    last_two = digits[-2:]
    if raw.startswith("+"):
        return f"+{digits[: _country_code_length(digits)]}***{last_two}"
    return f"***{last_two}"


def _redact_key_value(match: re.Match[str]) -> str:
    return f"{match.group('key')}{match.group('sep')}{REDACTED}"


def redact_text(text: str, *, extra_keys: frozenset[str] = frozenset()) -> str:
    """Redact secrets, tokens, artifact URLs and phone numbers from free text. Idempotent."""
    if not text:
        return text
    text = _PATTERN_PRIVATE_KEY.sub(REDACTED, text)
    text = _PATTERN_URL_USERINFO.sub(lambda m: f"{m.group('scheme')}{m.group('user')}:{REDACTED}@", text)
    text = _PATTERN_ARTIFACT_URL.sub(lambda m: f"{m.group('origin')}/[REDACTED-ARTIFACT-URL]", text)
    text = _PATTERN_URL_QUERY.sub(lambda m: f"{m.group('lead')}{m.group('name')}={REDACTED}", text)
    text = _PATTERN_KEY_VALUE.sub(_redact_key_value, text)
    if extra_keys:
        alternatives = "|".join(re.escape(key).replace("_", "[-_]") for key in sorted(extra_keys))
        text = re.sub(
            rf"(?P<key>\b(?:{alternatives}))(?P<sep>[\"']?\s{{0,3}}[=:]\s{{0,3}})(?P<value>\[REDACTED\]|[^\s,;&}}\])\"']+)",
            lambda m: f"{m.group('key')}{m.group('sep')}{REDACTED}",
            text,
            flags=re.IGNORECASE,
        )
    text = _PATTERN_BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _PATTERN_JWT.sub(REDACTED, text)
    text = _PATTERN_VENDOR_TOKENS.sub(REDACTED, text)
    return _PATTERN_PHONE.sub(_mask_phone, text)


def redact_value(
    value: object,
    *,
    key: str | None = None,
    extra_keys: frozenset[str] = frozenset(),
    _depth: int = 0,
) -> object:
    """Recursively redact a structured value. Never raises on odd input."""
    if key is not None and _is_sensitive_key(key, extra_keys):
        return REDACTED
    if _depth >= MAX_DEPTH:
        return "[TRUNCATED]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return redact_text(value, extra_keys=extra_keys)
    if isinstance(value, bytes | bytearray):
        return redact_text(bytes(value).decode("utf-8", errors="replace"), extra_keys=extra_keys)
    if isinstance(value, Mapping):
        return {
            str(k): redact_value(v, key=str(k), extra_keys=extra_keys, _depth=_depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [redact_value(v, extra_keys=extra_keys, _depth=_depth + 1) for v in value]
    try:
        return redact_text(str(value), extra_keys=extra_keys)
    except Exception:  # noqa: BLE001 - a log call must never fail because of an odd object
        return "[UNREPRESENTABLE]"


_STANDARD_RECORD_ATTRIBUTES = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message",
    "asctime",
    "taskName",
}


class RedactionFilter(logging.Filter):
    """Redacts the message, extra fields and exception text of every record it sees."""

    def __init__(self, extra_sensitive_keys: list[str] | tuple[str, ...] = ()) -> None:
        super().__init__()
        self._extra_keys = frozenset(_normalise_key(k) for k in extra_sensitive_keys if k)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - malformed format args must not break logging
            message = str(record.msg)
        record.msg = redact_text(message, extra_keys=self._extra_keys)
        record.args = ()
        for name in [n for n in vars(record) if n not in _STANDARD_RECORD_ATTRIBUTES]:
            setattr(record, name, redact_value(getattr(record, name), key=name, extra_keys=self._extra_keys))
        if record.exc_info and not record.exc_text:
            rendered = "".join(traceback.format_exception(*record.exc_info)).rstrip()
            record.exc_text = redact_text(rendered, extra_keys=self._extra_keys)
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text, extra_keys=self._extra_keys)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info, extra_keys=self._extra_keys)
        return True


# ------------------------------------------------------------------------- formatter


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp (UTC), level, logger, message, context, extras."""

    def __init__(self, *, indent: int | None = None) -> None:
        super().__init__()
        self._indent = indent

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(get_context())
        for name, value in vars(record).items():
            if name not in _STANDARD_RECORD_ATTRIBUTES and name not in payload:
                payload[name] = value
        if record.exc_info and not record.exc_text:
            record.exc_text = "".join(traceback.format_exception(*record.exc_info)).rstrip()
        if record.exc_text:
            payload["exception"] = record.exc_text
        return json.dumps(payload, default=str, indent=self._indent, ensure_ascii=False)


def build_logging_config(
    *, level: str = "INFO", pretty: bool = False, extra_sensitive_keys: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Django/gunicorn ``LOGGING`` dict. The redaction filter sits on every handler."""
    handler_filters = ["redact"]
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "redact": {
                "()": "apps.core.logging.RedactionFilter",
                "extra_sensitive_keys": list(extra_sensitive_keys),
            }
        },
        "formatters": {"json": {"()": "apps.core.logging.JsonFormatter", "indent": 2 if pretty else None}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": handler_filters,
            }
        },
        "root": {"handlers": ["console"], "level": level.upper()},
        "loggers": {
            "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
            "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
            "gunicorn.error": {"handlers": ["console"], "level": level.upper(), "propagate": False},
            "gunicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console"], "level": level.upper(), "propagate": False},
        },
    }
