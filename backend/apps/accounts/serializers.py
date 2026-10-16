"""Strict request serializers for the auth endpoints: exact fields, real strings, length limits.

Validation errors are deliberately uninformative (no field names, no echoed values): these endpoints face
unauthenticated callers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

INVALID = "Invalid request."


class StrictCharField(serializers.CharField):
    """JSON strings only: DRF's CharField would coerce a number such as ``123456`` into the text "123456"."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictSerializer(serializers.Serializer[Any]):
    def to_internal_value(self, data: Any) -> Any:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": [INVALID]})
        if set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": [INVALID]})  # never name the extra field
        return super().to_internal_value(data)


class TokenRequestSerializer(StrictSerializer):
    username = StrictCharField(max_length=254)  # the account's email address
    password = StrictCharField(max_length=256, trim_whitespace=False)
    mfa_code = StrictCharField(max_length=16, required=False, allow_blank=True, trim_whitespace=False)


class MfaConfirmSerializer(StrictSerializer):
    code = StrictCharField(max_length=16, trim_whitespace=False)


class RefreshBodySerializer(StrictSerializer):
    """Non-browser clients (``AUTH_TOKENS_IN_BODY``) may send the refresh token in the body."""

    refresh = StrictCharField(max_length=4096, required=False, trim_whitespace=False)


class ErrorSerializer(serializers.Serializer[Any]):
    """The contract's ``Error`` schema."""

    code = serializers.CharField()
    message = serializers.CharField()


class AuthenticatedSerializer(serializers.Serializer[Any]):
    authenticated = serializers.BooleanField()
    mfa_enrollment_required = serializers.BooleanField(required=False)
    mfa_enrollment_token = serializers.CharField(required=False)
    expires_in = serializers.IntegerField(required=False)


class MfaEnrollResponseSerializer(serializers.Serializer[Any]):
    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()
    issuer = serializers.CharField()


class MfaStateSerializer(serializers.Serializer[Any]):
    # ``required`` is the API's name for the field; it shadows DRF's ``Field.required`` flag only for typing.
    required = serializers.BooleanField()  # type: ignore[assignment]
    enrolled = serializers.BooleanField()


class SessionStateSerializer(serializers.Serializer[Any]):
    access_expires_at = serializers.DateTimeField()
    absolute_expires_at = serializers.DateTimeField()


class MeSerializer(serializers.Serializer[Any]):
    """``GET /auth/me``. Exactly these keys: nothing else about the account may leave the server."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField(allow_blank=True)
    roles = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.ListField(child=serializers.CharField())
    mfa = MfaStateSerializer()
    session = SessionStateSerializer()
