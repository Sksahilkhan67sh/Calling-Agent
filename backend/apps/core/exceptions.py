"""DRF exception handler: every API error is the contract's ``{code, message}``, never ``{detail}``."""

import logging
from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.core import error_codes

logger = logging.getLogger(__name__)


def safe_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)  # keeps Retry-After / WWW-Authenticate and the rollback
    if response is None:
        logger.exception("unhandled exception in API view")
        return Response(error_codes.INTERNAL_ERROR.body(), status=error_codes.INTERNAL_ERROR.status)
    response.data = error_codes.for_status(response.status_code).body()
    return response
