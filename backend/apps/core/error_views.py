"""Django-level error responses (404/400/403/500 and CSRF failure) as the contract's JSON ``Error``."""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, JsonResponse

from apps.core import error_codes

logger = logging.getLogger(__name__)


def _respond(error: error_codes.ApiError) -> JsonResponse:
    return JsonResponse(error.body(), status=error.status)


def bad_request(request: HttpRequest, exception: Any = None) -> JsonResponse:
    return _respond(error_codes.INVALID_REQUEST)


def permission_denied(request: HttpRequest, exception: Any = None) -> JsonResponse:
    return _respond(error_codes.FORBIDDEN)


def not_found(request: HttpRequest, exception: Any = None) -> JsonResponse:
    return _respond(error_codes.NOT_FOUND)


def server_error(request: HttpRequest) -> JsonResponse:
    return _respond(error_codes.INTERNAL_ERROR)


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    logger.info("csrf failure", extra={"reason": reason})  # Django's fixed reason strings, safe to log
    return _respond(error_codes.CSRF_FAILED)
