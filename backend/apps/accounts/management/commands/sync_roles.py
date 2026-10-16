from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts.services import sync_roles
from apps.audit.service import Actor


class Command(BaseCommand):
    help = "Create or update the role Groups and their permissions from the capability registry (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:
        result = sync_roles(actor=Actor.cli())
        if not result.changed:
            self.stdout.write("Roles already in sync.")
            return
        for role in result.groups_created:
            self.stdout.write(f"created group: {role}")
        for role, labels in result.permissions_added.items():
            self.stdout.write(f"{role}: +{len(labels)} permissions")
        for role, labels in result.permissions_removed.items():
            self.stdout.write(f"{role}: -{len(labels)} permissions (drift removed)")
