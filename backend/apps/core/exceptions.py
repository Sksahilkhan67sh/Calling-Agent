"""DRF exception handler that never leaks internals or request bodies."""

import logging
from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def safe_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is not None:
        return response
    logger.exception("unhandled exception in API view")
    return Response({"detail": "Internal server error."}, status=500)
