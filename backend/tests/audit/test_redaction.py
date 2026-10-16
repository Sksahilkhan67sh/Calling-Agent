"""No secret may reach the audit table, whatever the caller passes in before/after/metadata (P2-06)."""

import base64
import datetime
import decimal
import json
import secrets
import uuid

import pytest

from apps.audit import actions
from apps.audit.models import AuditEvent
from apps.audit.redaction import AUDIT_SENSITIVE_KEYS, MAX_PAYLOAD_BYTES, REDACTED, redact_payload
from apps.audit.service import Actor, record

pytestmark = pytest.mark.django_db


def stored(**payload):
    event = record(action=actions.USER_CREATED, actor=Actor.system("t"), **payload)
    return AuditEvent.objects.get(pk=event.pk)


@pytest.mark.integration
@pytest.mark.parametrize(
    "key",
    [
        "password",
        "new_password",
        "password_hash",
        "otp",
        "code",
        "totp",
        "seed",
        "secret",
        "secret_encrypted",
        "token",
        "access_token",
        "refresh",
        "api_key",
        "key_hash",
        "authorization",
        "cookie",
        "sessionid",
        "csrftoken",
        "provisioning_uri",
        "X-Api-Key",
        "Authorization",
        "__Host-access",
        "__Secure-refresh",
    ],
)
@pytest.mark.parametrize("field", ["before", "after", "metadata"])
def test_secret_keys_are_masked_in_every_payload_field(key, field):
    secret = secrets.token_urlsafe(24)
    event = stored(**{field: {key: secret, "status": "ok"}})
    payload = getattr(event, field)
    assert secret not in json.dumps(payload)
    assert payload["status"] == "ok" and REDACTED in json.dumps(payload)


@pytest.mark.integration
def test_nested_secrets_are_masked_but_ordinary_data_survives():
    secret, seed = secrets.token_urlsafe(24), secrets.token_hex(10).upper()
    event = stored(
        after={
            "user": {"email": "a@example.com", "roles": ["Admin"], "credentials": [{"password": secret}]},
            "mfa": {"seed": seed, "confirmed": True},
            "id": uuid.UUID(int=7),
        }
    )
    dump = json.dumps(event.after)
    assert secret not in dump and seed not in dump
    assert event.after["user"]["email"] == "a@example.com" and event.after["user"]["roles"] == ["Admin"]
    assert event.after["mfa"]["confirmed"] is True and event.after["id"] == str(uuid.UUID(int=7))


@pytest.mark.integration
def test_secret_shaped_values_under_harmless_keys_are_masked():
    token = secrets.token_urlsafe(30)
    seed = base64.b32encode(secrets.token_bytes(10)).decode()  # throwaway TOTP seed, generated per run
    event = stored(
        after={
            "note": f"Bearer {token}",
            "uri": f"otpauth://totp/Issuer:a@example.com?secret={seed}&issuer=Issuer",
            "phone": "+14155550123",
        }
    )
    dump = json.dumps(event.after)
    assert token not in dump and seed not in dump and "4155550123" not in dump


@pytest.mark.integration
def test_non_json_values_are_stored_safely():
    event = stored(
        after={
            "when": datetime.datetime(2026, 10, 11, 12, 0, tzinfo=datetime.UTC),
            "price": decimal.Decimal("1.50"),
            "tags": {"a"},
            "raw": b"bytes",
        }
    )
    assert event.after["when"].startswith("2026-10-11") and event.after["price"] == "1.50"
    assert event.after["tags"] == ["a"]


def test_none_and_empty_values():
    assert redact_payload(None) is None
    assert redact_payload({}) == {}


def test_oversized_payloads_are_replaced_by_a_marker():
    big = {"rows": ["x" * 100 for _ in range(400)]}
    result = redact_payload(big)
    assert result["_truncated"] is True and result["_original_bytes"] > MAX_PAYLOAD_BYTES
    assert redact_payload({"rows": ["x" * 100 for _ in range(100)]}) != result  # below the bound: kept


@pytest.mark.integration
def test_oversized_metadata_cannot_bloat_the_table():
    event = stored(metadata={"blob": "y" * (MAX_PAYLOAD_BYTES * 2)})
    assert event.metadata["_truncated"] is True and "blob" not in event.metadata


def test_sensitive_key_set_is_already_normalised():
    assert all(key == key.lower().replace("-", "_") for key in AUDIT_SENSITIVE_KEYS)
