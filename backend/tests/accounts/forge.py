"""Builds the tokens an attacker would try. Keys are generated per run; nothing secret is committed."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings

CLAIMS = ("token_type", "exp", "iat", "jti", "sub", "auth_epoch", "iss", "aud", "sid", "sat")


def payload(user, kind: str = "access", lifetime: int = 900, **override: Any) -> dict[str, Any]:
    now = int(time.time())
    data: dict[str, Any] = {
        "token_type": kind,
        "exp": now + lifetime,
        "iat": now,
        "jti": uuid.uuid4().hex,
        "sub": str(user.pk),
        "auth_epoch": user.auth_epoch,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "roles": [],
        "sid": uuid.uuid4().hex,
        "sat": now,
    }
    data.update(override)
    return {k: v for k, v in data.items() if v is not ...}  # ``claim=...`` removes the claim


def sign(data: dict[str, Any], key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(data, settings.JWT_SIGNING_KEY if key is None else key, algorithm=algorithm)


def unsigned(data: dict[str, Any]) -> str:
    return jwt.encode(data, key=None, algorithm="none")


def rs256(data: dict[str, Any]) -> tuple[str, bytes]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return jwt.encode(data, private, algorithm="RS256"), public_pem


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def hs256_with_secret(data: dict[str, Any], secret: bytes) -> str:
    """HS256 signed by hand (PyJWT refuses PEM keys as HMAC secrets): the classic key-confusion forgery."""
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(data).encode())
    signature = hmac.new(secret, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(signature)}"


def tamper_payload(token: str, **changes: Any) -> str:
    head, body, signature = token.split(".")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    data.update(changes)
    return f"{head}.{_b64(json.dumps(data).encode())}.{signature}"


def flip_signature(token: str) -> str:
    head, body, signature = token.split(".")
    return f"{head}.{body}.{signature[:-2]}{'A' if signature[-2] != 'A' else 'B'}{signature[-1]}"
