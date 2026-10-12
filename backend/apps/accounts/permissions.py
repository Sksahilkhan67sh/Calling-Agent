"""Capability-based DRF permissions (Django-Backend-Design §4.2). Default deny, fail closed."""

from __future__ import annotations

import logging
from functools import cache
from typing import TYPE_CHECKING, Any

from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.roles import CAPABILITY_NAMES

if TYPE_CHECKING:
    from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class CapabilityPermission(BasePermission):
    """Allows an authenticated principal holding at least one of ``capabilities``.

    A principal is a human ``User`` or an API client; both expose ``has_capability(name)``. Anything
    unexpected (no such method, an exception) denies. Object-level scoping is the queryset's job
    (``ScopedQuerySet.for_user``); this class only answers "may this caller perform the action at all".
    """

    capabilities: tuple[str, ...] = ()

    def has_permission(self, request: Request, view: APIView) -> bool:
        try:
            principal = request.user
            if principal is None or not getattr(principal, "is_authenticated", False):
                return False
            check = getattr(principal, "has_capability", None)
            if check is None:
                return False
            return any(check(name) is True for name in self.capabilities)
        except APIException:
            raise
        except Exception:
            logger.exception(
                "capability check failed; denying",
                extra={"capabilities": list(self.capabilities), "view": type(view).__name__},
            )
            return False


@cache
def _build(names: tuple[str, ...]) -> type[CapabilityPermission]:
    return type("HasCapability[" + "|".join(names) + "]", (CapabilityPermission,), {"capabilities": names})


def HasCapability(*names: str) -> type[CapabilityPermission]:  # noqa: N802 - used like a class in permission_classes
    """``permission_classes = [HasCapability("campaigns.create")]``; several names mean "any of"."""
    if not names:
        raise ValueError("HasCapability needs at least one capability name")
    unknown = [n for n in names if n not in CAPABILITY_NAMES]
    if unknown:
        raise ValueError(f"Unknown capability: {unknown}")
    return _build(tuple(dict.fromkeys(names)))


class ObjectScoped(BasePermission):
    """Backstop for views that fetch objects outside ``ScopedViewMixin``.

    An object outside the caller's ``for_user`` scope is reported as *not found* (never 403), so the
    existence of other users' rows cannot be probed.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        manager = type(obj)._default_manager
        for_user = getattr(manager, "for_user", None)
        if for_user is None or not for_user(request.user).filter(pk=obj.pk).exists():
            raise NotFound()
        return True
