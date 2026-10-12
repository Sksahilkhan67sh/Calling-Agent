"""Field-level encryption and the phone blind index.

Design references: Django-Backend-Design §3 (encrypted columns, blind index),
Environment-Config §2.8 (``FIELD_ENCRYPTION_KEYS``, ``PHONE_HMAC_KEY``).

Ciphertext format (versioned so it can evolve)::

    v1:<key_id>:<base64url nonce>:<base64url ciphertext+tag>

AES-256-GCM, 96-bit random nonce, 128-bit tag. The associated data binds the
format version, the key id and a caller-supplied context (for example
``contact.phone_encrypted``), so a ciphertext copied into another column or
re-labelled with another key id fails authentication.

This module never logs and never puts plaintext or key material in errors.
The blind index takes ALREADY CANONICAL input; E.164 normalisation of phone
numbers belongs to the ``contacts`` app (Phase 3).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
from collections.abc import Sequence

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .settings_utils import ConfigError

__all__ = [
    "CryptoError",
    "DecryptionError",
    "FieldCipher",
    "KeyConfigError",
    "blind_index",
    "parse_encryption_keys",
    "parse_hmac_key",
]

FORMAT_VERSION = "v1"
KEY_BYTES = 32
NONCE_BYTES = 12
MIN_HMAC_KEY_BYTES = 32
_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
_PURPOSE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


class CryptoError(Exception):
    """Base class. Messages never contain plaintext or key material."""


class DecryptionError(CryptoError):
    """Ciphertext is malformed, tampered with, bound to other context, or uses an unknown key."""


class KeyConfigError(ConfigError):
    """Key configuration is invalid. Names the variable, never a value."""


def _b64decode(data: str, *, urlsafe: bool) -> bytes:
    """Strict base64: characters outside the alphabet raise instead of being skipped."""
    if urlsafe:
        data = data.replace("-", "+").replace("_", "/")
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.b64decode(padded.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError):
        raise ValueError("invalid base64") from None


def parse_encryption_keys(raw: str, *, variable: str = "FIELD_ENCRYPTION_KEYS") -> list[tuple[str, bytes]]:
    """Parse ``id1:base64key1,id2:base64key2`` (newest first) into ``[(id, key_bytes)]``."""
    entries = [item.strip() for item in raw.split(",") if item.strip()]
    if not entries:
        raise KeyConfigError(f"{variable} must contain at least one key")
    keys: list[tuple[str, bytes]] = []
    seen_ids: set[str] = set()
    seen_material: set[bytes] = set()
    for position, entry in enumerate(entries, start=1):
        key_id, separator, encoded = entry.partition(":")
        if not separator or not _KEY_ID_PATTERN.match(key_id):
            raise KeyConfigError(f"{variable} entry {position} must look like <key_id>:<base64 key>")
        try:
            key = _b64decode(encoded, urlsafe=False)
        except ValueError:
            raise KeyConfigError(f"{variable} entry {position} is not valid base64") from None
        if len(key) != KEY_BYTES:
            raise KeyConfigError(f"{variable} entry {position} must decode to {KEY_BYTES} bytes")
        if key_id in seen_ids:
            raise KeyConfigError(f"{variable} entry {position} repeats a key id")
        if key in seen_material:
            raise KeyConfigError(f"{variable} entry {position} repeats key material")
        seen_ids.add(key_id)
        seen_material.add(key)
        keys.append((key_id, key))
    return keys


def parse_hmac_key(raw: str, *, variable: str = "PHONE_HMAC_KEY") -> bytes:
    try:
        key = _b64decode(raw.strip(), urlsafe=False)
    except ValueError:
        raise KeyConfigError(f"{variable} is not valid base64") from None
    if len(key) < MIN_HMAC_KEY_BYTES:
        raise KeyConfigError(f"{variable} must decode to at least {MIN_HMAC_KEY_BYTES} bytes")
    return key


class FieldCipher:
    """Encrypts with the newest key; decrypts with whichever key the header names."""

    def __init__(self, keys: Sequence[tuple[str, bytes]]) -> None:
        if not keys:
            raise KeyConfigError("FieldCipher needs at least one key")
        self._ciphers: dict[str, AESGCM] = {}
        for key_id, key in keys:
            if not _KEY_ID_PATTERN.match(key_id) or len(key) != KEY_BYTES:
                raise KeyConfigError("FieldCipher received an invalid key entry")
            if key_id in self._ciphers:
                raise KeyConfigError("FieldCipher received a repeated key id")
            self._ciphers[key_id] = AESGCM(key)
        self._current_id = keys[0][0]

    @property
    def current_key_id(self) -> str:
        return self._current_id

    @staticmethod
    def _associated_data(key_id: str, context: str) -> bytes:
        return f"{FORMAT_VERSION}|{key_id}|{context}".encode()

    def encrypt(self, plaintext: str, *, context: str) -> str:
        """``context`` is mandatory (e.g. ``"contact.phone_encrypted"``)."""
        if not context:
            raise CryptoError("an encryption context is required")
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._ciphers[self._current_id].encrypt(
            nonce, plaintext.encode("utf-8"), self._associated_data(self._current_id, context)
        )
        return ":".join(
            (
                FORMAT_VERSION,
                self._current_id,
                base64.urlsafe_b64encode(nonce).decode("ascii").rstrip("="),
                base64.urlsafe_b64encode(sealed).decode("ascii").rstrip("="),
            )
        )

    def decrypt(self, token: str, *, context: str) -> str:
        parts = token.split(":")
        if len(parts) != 4 or parts[0] != FORMAT_VERSION:
            raise DecryptionError("ciphertext could not be decrypted")
        _, key_id, nonce_part, sealed_part = parts
        cipher = self._ciphers.get(key_id)
        if cipher is None:
            raise DecryptionError("ciphertext could not be decrypted")
        try:
            nonce = _b64decode(nonce_part, urlsafe=True)
            sealed = _b64decode(sealed_part, urlsafe=True)
            if len(nonce) != NONCE_BYTES:
                raise ValueError("bad nonce length")
            plaintext = cipher.decrypt(nonce, sealed, self._associated_data(key_id, context))
            return plaintext.decode("utf-8")
        except (ValueError, InvalidTag):
            raise DecryptionError("ciphertext could not be decrypted") from None

    def needs_rotation(self, token: str) -> bool:
        """True when the token was sealed with a key that is no longer the newest."""
        parts = token.split(":")
        return len(parts) == 4 and parts[1] != self._current_id


def blind_index(value: str, *, key: bytes, purpose: str) -> str:
    """Deterministic keyed hash for equality lookups on encrypted columns.

    HMAC-SHA256 over ``purpose NUL value`` (domain separation), returned as 64 hex chars.
    ``value`` must already be canonical (for phones: E.164, done in Phase 3).
    Changing ``PHONE_HMAC_KEY`` invalidates every stored index: it is a planned
    re-computation, not an in-place rotation (see docs/phase-1/DECISIONS.md).
    """
    if len(key) < MIN_HMAC_KEY_BYTES:
        raise CryptoError("blind index key is too short")
    if not _PURPOSE_PATTERN.match(purpose):
        raise CryptoError("blind index purpose is invalid")
    message = purpose.encode("ascii") + b"\x00" + value.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()
