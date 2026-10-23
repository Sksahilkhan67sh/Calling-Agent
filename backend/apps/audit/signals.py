from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .services import record


@receiver(m2m_changed, sender=get_user_model().groups.through)
def role_assignment_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action in ("post_add", "post_remove", "post_clear"):
        # No request context here, so the actor is "system"
        record(f"role.{action[5:]}", "user_groups", instance.pk, after={"reverse": reverse, "pks": sorted(pk_set or [])})
