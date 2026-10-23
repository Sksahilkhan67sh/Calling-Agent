from django.db import transaction
from django.db.models import Q

from apps.audit.services import record

from .models import Suppression


def is_suppressed(contact):
    return Suppression.objects.filter(Q(contact=contact) | Q(phone_hmac=bytes(contact.phone_hmac))).exists()


def suppress(contact, reason, source, *, actor=None, request=None):
    with transaction.atomic():
        suppression, created = Suppression.objects.get_or_create(
            contact=contact, defaults={"phone_hmac": contact.phone_hmac, "reason": reason, "source": source}
        )
        if created:
            record("suppression.add", "contact", contact.pk, actor=actor, request=request,
                   after={"reason": reason, "source": source})
    return suppression, created
