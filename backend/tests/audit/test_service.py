"""audit.record / audited: same-transaction, fail-closed, request context (P2-06)."""

import getpass
import uuid
from unittest import mock

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, transaction

from apps.accounts.models import User
from apps.accounts.roles import ROLE_CAMPAIGN_MANAGER
from apps.accounts.services import sync_roles
from apps.audit import actions
from apps.audit.context import request_info
from apps.audit.models import AuditEvent
from apps.audit.service import Actor, AuditError, audited, record
from apps.core.logging import context as log_context

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_record_stores_every_field(db):
    target = uuid.uuid4()
    with request_info("203.0.113.9", "Mozilla/5.0"), log_context(request_id="req-abc123"):
        event = record(
            action=actions.USER_ROLE_ASSIGNED,
            actor=Actor.system("system:cli:ops"),
            object_type="user",
            object_id=target,
            before={"roles": []},
            after={"roles": ["Admin"]},
            metadata={"reason": "bootstrap"},
        )
    stored = AuditEvent.objects.get(pk=event.pk)
    assert (stored.actor_type, stored.actor_id, stored.actor_label) == ("system", None, "system:cli:ops")
    assert (stored.object_type, stored.object_id) == ("user", str(target))
    assert stored.before == {"roles": []} and stored.after == {"roles": ["Admin"]}
    assert stored.metadata == {"reason": "bootstrap"} and stored.outcome == "success"
    assert (stored.source_ip, stored.request_id, stored.user_agent) == (
        "203.0.113.9",
        "req-abc123",
        "Mozilla/5.0",
    )


def test_without_a_request_the_request_fields_are_empty(event):
    assert event.source_ip is None and event.user_agent == "" and event.request_id == ""


def test_user_agent_and_labels_are_bounded_and_stripped_of_control_characters(db):
    with request_info(None, "Evil\r\nX-Injected: 1\x00" + "A" * 1000):
        event = record(
            action=actions.AUTH_LOGIN_FAILURE, actor=Actor.anonymous("a\nb" + "x" * 500), outcome="failure"
        )
    assert len(event.user_agent) == 256 and "\n" not in event.user_agent and "\x00" not in event.user_agent
    assert len(event.actor_label) == 254 and "\n" not in event.actor_label and event.outcome == "failure"


def test_actor_constructors(make_user_factory):
    user = make_user_factory()
    actor = Actor.user(user)
    assert (actor.type, actor.id, actor.label) == ("user", user.pk, user.email)
    client_id = uuid.uuid4()
    assert Actor.api_client(client_id, "crm").type == "api_client"
    assert Actor.anonymous().type == "anonymous" and Actor.anonymous().id is None


def test_cli_actor_names_the_operating_system_user():
    assert Actor.cli().label == f"system:cli:{getpass.getuser()}"
    with mock.patch("apps.audit.service.getpass.getuser", side_effect=KeyError("no passwd entry")):
        assert Actor.cli().label == "system:cli:unknown"


@pytest.mark.parametrize("bad_action", ["", "user.creatd", "AUTH.LOGIN.SUCCESS", "rm -rf"])
def test_unknown_actions_are_refused_and_nothing_is_written(bad_action, db):
    with pytest.raises(AuditError, match="Unknown audit action"):
        record(action=bad_action, actor=Actor.system("t"))
    assert AuditEvent.objects.count() == 0


def test_unknown_outcome_is_refused(db):
    with pytest.raises(AuditError, match="outcome"):
        record(action=actions.AUTH_LOGOUT, actor=Actor.system("t"), outcome="maybe")


def test_record_outside_a_transaction_is_refused(db):
    fake = mock.Mock(in_atomic_block=False)
    with (
        mock.patch("apps.audit.service.transaction.get_connection", return_value=fake),
        pytest.raises(AuditError, match="inside transaction.atomic"),
    ):
        record(action=actions.AUTH_LOGOUT, actor=Actor.system("t"))
    assert AuditEvent.objects.count() == 0


def test_audited_commits_the_change_and_the_event_together(db):
    with audited(action=actions.USER_CREATED, actor=Actor.system("t"), object_type="group") as scope:
        group = Group.objects.create(name="Temp")
        scope.object_id = group.pk
        scope.after = {"name": group.name}
    event = AuditEvent.objects.get(action=actions.USER_CREATED)
    assert Group.objects.filter(name="Temp").exists() and event.object_id == str(group.pk)
    assert event.after == {"name": "Temp"}


def test_failed_audit_rolls_the_change_back(db):
    with pytest.raises(AuditError), audited(action=actions.USER_CREATED, actor=Actor.system("t")) as scope:
        Group.objects.create(name="Doomed")
        scope.action = "not.registered"  # the audit write is refused...
    assert not Group.objects.filter(name="Doomed").exists()  # ...so the change is gone
    assert AuditEvent.objects.count() == 0


def test_database_failure_during_the_audit_write_rolls_the_change_back(db):
    with mock.patch("apps.audit.service.AuditEvent.objects") as manager:
        manager.using.return_value.create.side_effect = DatabaseError("audit table unavailable")
        with pytest.raises(DatabaseError), audited(action=actions.USER_CREATED, actor=Actor.system("t")):
            Group.objects.create(name="Doomed")
    assert not Group.objects.filter(name="Doomed").exists()


def test_failed_change_writes_no_success_event(db):
    with (
        pytest.raises(ValueError, match="boom"),
        audited(action=actions.USER_CREATED, actor=Actor.system("t")),
    ):
        Group.objects.create(name="Half")
        raise ValueError("boom")
    assert not Group.objects.filter(name="Half").exists() and AuditEvent.objects.count() == 0


def test_a_failure_event_can_be_recorded_after_a_failed_change(db):
    with pytest.raises(ValueError), audited(action=actions.USER_CREATED, actor=Actor.system("t")):
        raise ValueError("boom")
    with transaction.atomic():
        record(action=actions.USER_CREATED, actor=Actor.system("t"), outcome="failure")
    assert AuditEvent.objects.get().outcome == "failure"


def test_sync_roles_writes_one_event_only_when_something_changed(db):
    first = sync_roles()
    events = AuditEvent.objects.filter(action=actions.RBAC_SYNC)
    assert first.changed and events.count() == 1
    event = events.get()
    assert event.actor_label == "sync_roles" and event.object_type == "role_matrix"
    assert sorted(event.after["groups_created"]) == sorted(first.groups_created)
    sync_roles()
    assert events.count() == 1  # a no-op run is not an event


def test_sync_roles_audit_failure_rolls_the_sync_back(db):
    with (
        mock.patch("apps.accounts.services.record", side_effect=AuditError("down")),
        pytest.raises(AuditError),
    ):
        sync_roles()
    assert not Group.objects.filter(name=ROLE_CAMPAIGN_MANAGER).exists()


@pytest.fixture
def make_user_factory(db):
    return lambda: User.objects.create_user("actor@example.com", "correct horse battery staple 7")
