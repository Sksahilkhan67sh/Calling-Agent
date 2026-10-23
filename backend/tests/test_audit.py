import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError

from apps.audit.models import AuditEvent

from .conftest import csrf


def test_login_and_logout_write_audit_rows(make_user, login, client):
    u = make_user()
    login()
    client.post("/v1/auth/logout", **csrf(client))
    rows = AuditEvent.objects.filter(object_id=str(u.pk))
    assert set(rows.values_list("action", flat=True)) == {"auth.login", "auth.logout"}
    assert rows.first().actor == "u1" and rows.first().source_ip == "127.0.0.1"


def test_failed_mfa_is_audited(make_user, login):
    u = make_user(role="Admin")
    login(mfa_code="000000")
    assert AuditEvent.objects.filter(action="auth.mfa_failed", object_id=str(u.pk)).exists()


def test_role_assignment_is_audited(make_user):
    u = make_user()
    u.groups.add(Group.objects.get(name="Admin"))
    e = AuditEvent.objects.get(action="role.add", object_id=str(u.pk))
    assert e.after["pks"] == [Group.objects.get(name="Admin").pk]


def test_audit_rows_cannot_be_updated_or_deleted(make_user, login):
    make_user()
    login()
    with pytest.raises(DatabaseError):
        AuditEvent.objects.update(action="x")
    with pytest.raises(DatabaseError):
        AuditEvent.objects.all().delete()
