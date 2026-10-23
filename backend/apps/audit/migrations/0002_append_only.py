from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [
        migrations.RunSQL(
            """
            CREATE FUNCTION audit_event_append_only() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'audit_event is append-only'; END $$ LANGUAGE plpgsql;
            CREATE TRIGGER audit_event_no_update_delete BEFORE UPDATE OR DELETE ON audit_event
            FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();
            """,
            "DROP TRIGGER audit_event_no_update_delete ON audit_event; DROP FUNCTION audit_event_append_only();",
        )
    ]
