"""Object-level scoping contract: ``Model.objects.for_user(user)`` (Django-Backend-Design §4.2).

Every model whose rows are shown to users has a manager built from a ``ScopedQuerySet`` subclass, and
every DRF view over such a model uses ``ScopedViewMixin`` so its queryset can only be reached through
``for_user``. Rows outside the scope are *absent* (404), never forbidden (403).
"""

from __future__ import annotations

from typing import Any, ClassVar, Self, TypeVar

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from rest_framework.generics import GenericAPIView

_M = TypeVar("_M", bound=models.Model)


class ScopedQuerySet(models.QuerySet[_M]):
    """Subclasses implement ``scope_to_user``; set ``view_all_capability`` for the "sees everything" role."""

    view_all_capability: ClassVar[str | None] = None

    def for_user(self, user: Any) -> Self:
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        all_capability = self.view_all_capability
        if all_capability is not None and user.has_capability(all_capability):
            return self.all()
        return self.scope_to_user(user)

    def scope_to_user(self, user: Any) -> Self:
        raise NotImplementedError(f"{type(self).__name__} must implement scope_to_user()")


class ScopedViewMixin(GenericAPIView[Any]):
    """Put before the DRF generic view: ``class V(ScopedViewMixin, RetrieveAPIView)``."""

    def get_queryset(self) -> models.QuerySet[Any]:
        queryset = super().get_queryset()
        if not isinstance(queryset, ScopedQuerySet):
            raise ImproperlyConfigured(
                f"{type(self).__name__}.queryset must come from a manager built on ScopedQuerySet"
            )
        return queryset.for_user(self.request.user)
