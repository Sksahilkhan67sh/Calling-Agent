"""Layer 2: PostgreSQL itself refuses UPDATE, DELETE and TRUNCATE, even for raw SQL (P2-06)."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def run(sql: str, params=None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_raw_update_is_blocked_by_the_trigger(event):
    with pytest.raises(IntegrityError, match="append-only: UPDATE"), transaction.atomic():
        run("UPDATE audit_event SET action = 'tampered' WHERE id = %s", [event.pk])
    event.refresh_from_db()
    assert event.action == "user.created"


def test_raw_delete_is_blocked_by_the_trigger(event):
    with pytest.raises(IntegrityError, match="append-only: DELETE"), transaction.atomic():
        run("DELETE FROM audit_event WHERE id = %s", [event.pk])


def test_truncate_is_blocked_by_the_trigger(event):
    with pytest.raises(IntegrityError, match="append-only: TRUNCATE"), transaction.atomic():
        run("TRUNCATE audit_event")
    with pytest.raises(IntegrityError, match="append-only: TRUNCATE"), transaction.atomic():
        run("TRUNCATE audit_event, accounts_user CASCADE")


def test_a_blocked_update_of_every_row_changes_nothing(event):
    with pytest.raises(IntegrityError), transaction.atomic():
        run("UPDATE audit_event SET outcome = 'failure'")
    event.refresh_from_db()
    assert event.outcome == "success"


def test_raw_insert_still_works(db):
    run(
        "INSERT INTO audit_event (id, actor_type, action, metadata, outcome, actor_label, object_type, "
        "object_id, request_id, user_agent) VALUES (gen_random_uuid(), 'system', 'rbac.sync', '{}', "
        "'success', '', '', '', '', '')"
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM audit_event")
        assert cursor.fetchone()[0] == 1


def test_triggers_are_enabled_always_so_replication_mode_cannot_skip_them(db):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname, tgenabled FROM pg_trigger "
            "WHERE tgrelid = 'audit_event'::regclass AND NOT tgisinternal ORDER BY tgname"
        )
        rows = cursor.fetchall()
    assert rows == [("audit_event_no_truncate", "A"), ("audit_event_no_update_delete", "A")]


def test_it_is_the_trigger_that_protects_the_row_not_something_else(event):
    """Dropping the trigger (owner-only, explicit) lets the same UPDATE through: proof of causality."""
    with transaction.atomic():
        run("DROP TRIGGER audit_event_no_update_delete ON audit_event")
        run("UPDATE audit_event SET action = 'tampered' WHERE id = %s", [event.pk])
        with connection.cursor() as cursor:
            cursor.execute("SELECT action FROM audit_event WHERE id = %s", [event.pk])
            assert cursor.fetchone()[0] == "tampered"
        transaction.set_rollback(True)  # DDL is transactional: restores the trigger and the row
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgname = 'audit_event_no_update_delete'")
        assert cursor.fetchone()[0] == 1


def test_trigger_migration_reverses_and_reapplies(event):
    target, previous = ("audit", "0002_append_only_triggers"), ("audit", "0001_initial")
    executor = MigrationExecutor(connection)
    executor.migrate([previous])
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'audit_event'::regclass AND NOT tgisinternal"
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM pg_proc WHERE proname = 'audit_event_block_mutation'")
        assert cursor.fetchone()[0] == 0
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    with pytest.raises(IntegrityError), transaction.atomic():
        run("DELETE FROM audit_event")
