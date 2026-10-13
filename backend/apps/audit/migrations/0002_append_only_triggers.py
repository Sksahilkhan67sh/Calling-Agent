"""Layer 2 of the audit tamper protection: the database refuses to change or remove audit rows.

ENABLE ALWAYS makes the triggers fire even when a session sets ``session_replication_role = replica``
(the usual way to skip triggers). The table owner or a superuser can still drop them explicitly; that is
why the application role is neither (deploy/sql/roles.sql, P2-17) and why it also lacks the privileges.

Reverse (reviewer/operator only, e.g. when rolling this migration back) drops the triggers and function.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION audit_event_block_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_event is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER audit_event_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION audit_event_block_mutation();

CREATE TRIGGER audit_event_no_truncate
    BEFORE TRUNCATE ON audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION audit_event_block_mutation();

ALTER TABLE audit_event ENABLE ALWAYS TRIGGER audit_event_no_update_delete;
ALTER TABLE audit_event ENABLE ALWAYS TRIGGER audit_event_no_truncate;
"""

REVERSE = """
DROP TRIGGER audit_event_no_truncate ON audit_event;
DROP TRIGGER audit_event_no_update_delete ON audit_event;
DROP FUNCTION audit_event_block_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, reverse_sql=REVERSE)]
