"""JSON-only request parsing with a hard size limit, for the credential endpoints."""

from __future__ import annotations

import io
from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser

MAX_BODY_BYTES = 8 * 1024


class PayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "Request body too large."
    default_code = "payload_too_large"


class BoundedJSONParser(JSONParser):
    """Reads at most ``MAX_BODY_BYTES`` (even when the client sends no Content-Length) and turns
    pathological nesting into a 400 instead of a recursion error."""

    def parse(self, stream: Any, media_type: Any = None, parser_context: Any = None) -> Any:
        data = stream.read(MAX_BODY_BYTES + 1)
        if len(data) > MAX_BODY_BYTES:
            raise PayloadTooLarge
        try:
            return super().parse(io.BytesIO(data), media_type, parser_context)
        except RecursionError:
            raise ParseError from None
