from django.db import migrations

ROLES = ["Campaign Manager", "Admin", "Sales/Follow-up", "System"]


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLES:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    # Not reversible on purpose: dropping groups would silently drop role assignments
    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
