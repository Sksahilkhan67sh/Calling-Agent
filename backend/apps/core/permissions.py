"""Default-deny permissions.

Every DRF view must declare its permissions. ``DefaultDeny`` is the DRF default so a
forgotten declaration yields 403, and tests/test_default_deny.py fails the build.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

if TYPE_CHECKING:
    from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class DefaultDeny(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        if settings.DEBUG:  # developer hint goes to the log; the response never explains itself
            logger.warning("%s declares no permission_classes (default deny)", type(view).__name__)
        return False


class PublicEndpoint(BasePermission):
    """Explicit anonymous access. Allowed only for the allowlist in tests/test_default_deny.py."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return True
