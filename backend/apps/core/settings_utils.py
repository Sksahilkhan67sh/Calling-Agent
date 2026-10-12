"""Environment readers for Django settings.

Rules (Environment-Config §2, Django-Backend-Design §4.4):
- A missing or malformed variable stops the process at start-up.
- Error messages name the variable and never include its value, because the
  value may be a secret.
- Every variable read is recorded in ``READ_VARIABLES`` so a test can prove
  ``docs/phase-1/ENV-VARIABLES.md`` lists everything the settings read.

This module must not import Django: settings import it before Django is set up.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "ConfigError",
    "READ_VARIABLES",
    "VariableUse",
    "as_bool",
    "as_csv_hosts",
    "as_int",
    "as_list",
    "as_origins",
    "looks_like_placeholder",
    "optional",
    "reject_placeholder",
    "required",
]


class ConfigError(Exception):
    """Invalid or missing configuration. The message never contains a value."""


@dataclass(frozen=True)
class VariableUse:
    name: str
    secret: bool


READ_VARIABLES: dict[str, VariableUse] = {}

_PLACEHOLDER_PATTERN = re.compile(
    r"(change[-_ ]?me|changeme|placeholder|replace[-_ ]?me|your[-_ ]?(secret|key|token)|"
    r"example|dummy|insecure|todo|xxxx)",
    re.IGNORECASE,
)
_HOST_PATTERN = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")
_ORIGIN_PATTERN = re.compile(r"^https?://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]{1,5})?$")


def _record(name: str, secret: bool) -> None:
    READ_VARIABLES[name] = VariableUse(name=name, secret=secret)


def looks_like_placeholder(value: str) -> bool:
    """True for values such as ``change-me-dev-only`` that must never reach production."""
    return bool(_PLACEHOLDER_PATTERN.search(value))


def reject_placeholder(name: str, value: str) -> None:
    if looks_like_placeholder(value):
        raise ConfigError(f"{name} still holds a placeholder value; set a real value")


def _environ(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def required(name: str, *, secret: bool = False, env: Mapping[str, str] | None = None) -> str:
    _record(name, secret)
    value = _environ(env).get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required but missing or empty")
    return value


def optional(
    name: str, default: str = "", *, secret: bool = False, env: Mapping[str, str] | None = None
) -> str:
    _record(name, secret)
    value = _environ(env).get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def as_int(
    name: str,
    default: int | None = None,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Read an integer. ``default=None`` makes the variable required."""
    _record(name, False)
    raw = _environ(env).get(name, "").strip()
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is required but missing or empty")
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be at most {maximum}")
    return value


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def as_bool(name: str, default: bool | None = None, *, env: Mapping[str, str] | None = None) -> bool:
    """Read a boolean. ``default=None`` makes the variable required."""
    _record(name, False)
    raw = _environ(env).get(name, "").strip().lower()
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is required but missing or empty")
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"{name} must be a boolean (true/false)")


def as_list(
    name: str, default: list[str] | None = None, *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Comma-separated list, whitespace trimmed, empty items dropped."""
    _record(name, False)
    raw = _environ(env).get(name)
    if raw is None or not raw.strip():
        if default is None:
            raise ConfigError(f"{name} is required but missing or empty")
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def as_csv_hosts(
    name: str, default: list[str] | None = None, *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Host list for ``ALLOWED_HOSTS``: no wildcards, no schemes, no ports, no paths."""
    hosts = as_list(name, default, env=env)
    if not hosts:
        raise ConfigError(f"{name} must list at least one host")
    for host in hosts:
        if "*" in host:
            raise ConfigError(f"{name} must not contain wildcards")
        if not _HOST_PATTERN.match(host):
            raise ConfigError(f"{name} contains an invalid host entry")
    return hosts


def as_origins(
    name: str, default: list[str] | None = None, *, env: Mapping[str, str] | None = None
) -> list[str]:
    """Browser origins (``scheme://host[:port]``): no wildcard, path, query or trailing slash."""
    origins = as_list(name, default, env=env)
    for origin in origins:
        if "*" in origin or not _ORIGIN_PATTERN.match(origin):
            raise ConfigError(
                f"{name} entries must be origins like https://host[:port], "
                "without wildcards, paths or a trailing slash"
            )
    return origins
