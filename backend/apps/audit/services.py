from rest_framework.throttling import BaseThrottle

from .models import AuditEvent


def record(action, object_type, object_id, *, actor=None, before=None, after=None, request=None):
    AuditEvent.objects.create(
        actor=actor.get_username() if actor else "system",
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before=before,
        after=after,
        source_ip=BaseThrottle().get_ident(request)[:45] if request else None,  # honours NUM_PROXIES
    )
