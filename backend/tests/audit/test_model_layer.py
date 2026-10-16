"""Layer 1 of the tamper protection: the model and queryset refuse changes and deletes (P2-06)."""

import uuid

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from apps.audit import actions
from apps.audit.models import AuditEvent, AuditImmutableError
from apps.audit.service import Actor, record

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_event_time_is_set_by_the_database_not_the_caller(frozen_time):
    event = record(action=actions.USER_CREATED, actor=Actor.system("t"))
    assert event.occurred_at is not None and event.occurred_at.tzinfo is not None
    frozen_now = frozen_time.time_to_freeze.replace(tzinfo=event.occurred_at.tzinfo)
    assert event.occurred_at != frozen_now  # the database clock was used, not the (frozen) application clock


def test_saving_an_existing_event_is_refused(event):
    event.action = actions.USER_DEACTIVATED
    with pytest.raises(AuditImmutableError, match="modified"):
        event.save()
    assert AuditEvent.objects.get(pk=event.pk).action == actions.USER_CREATED


def test_instance_delete_is_refused(event):
    with pytest.raises(AuditImmutableError, match="deleted"):
        event.delete()
    assert AuditEvent.objects.filter(pk=event.pk).exists()


@pytest.mark.parametrize(
    "operation",
    [
        lambda qs: qs.update(action="x"),
        lambda qs: qs.delete(),
        lambda qs: qs.bulk_update([], ["action"]),
        lambda qs: qs._raw_delete(qs.db),
    ],
    ids=["update", "delete", "bulk_update", "raw_delete"],
)
def test_queryset_mutations_are_refused(operation, event):
    with pytest.raises(AuditImmutableError):
        operation(AuditEvent.objects.all())
    assert AuditEvent.objects.count() == 1


def test_manager_level_shortcuts_are_refused_too(event):
    with pytest.raises(AuditImmutableError):
        AuditEvent.objects.update_or_create(id=event.pk, defaults={"action": actions.AUTH_LOGOUT})
    with pytest.raises(AuditImmutableError, match="upserted"):
        AuditEvent.objects.bulk_create(
            [AuditEvent(id=event.pk, actor_type="system", action="x")],
            update_conflicts=True,
            update_fields=["action"],
            unique_fields=["id"],
        )
    assert AuditEvent.objects.get(pk=event.pk).action == actions.USER_CREATED


def test_plain_inserts_remain_possible(db):
    AuditEvent.objects.bulk_create([AuditEvent(actor_type="system", action=actions.RBAC_SYNC)])
    assert AuditEvent.objects.count() == 1


def test_reusing_an_existing_id_cannot_overwrite(event):
    clone = AuditEvent(
        id=event.pk, actor_type="system", action=actions.AUTH_LOGOUT, occurred_at=timezone.now()
    )
    with pytest.raises(Exception, match="duplicate key|UNIQUE|unique"):
        clone.save(force_insert=True)


def test_only_a_view_permission_exists_and_nothing_references_users():
    codenames = set(
        Permission.objects.filter(content_type__app_label="audit").values_list("codename", flat=True)
    )
    assert codenames == {"view_auditevent"}
    assert not [f for f in AuditEvent._meta.get_fields() if f.is_relation]
    AuditEvent.objects.create(
        actor_type="user", actor_id=uuid.uuid4(), action=actions.AUTH_LOGOUT
    )  # no FK needed


def test_string_form_names_the_action_and_actor(event):
    assert str(event) == "user.created by system:test"
