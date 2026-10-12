"""A minimal scoped model: a Campaign Manager owns rows; whoever holds campaigns.view_all sees all."""

import uuid
from typing import Any, ClassVar, Self

from django.conf import settings
from django.db import models

from apps.accounts.querysets import ScopedQuerySet


class ThingQuerySet(ScopedQuerySet["ScopedThing"]):
    view_all_capability: ClassVar[str | None] = "campaigns.view_all"

    def scope_to_user(self, user: Any) -> Self:
        if user.has_capability("campaigns.view_own"):
            return self.filter(owner=user)
        return self.none()


class ScopedThing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    title = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="draft")

    objects = ThingQuerySet.as_manager()  # type: ignore[misc]
