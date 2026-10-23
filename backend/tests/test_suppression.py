import pytest
from django.db.models import ProtectedError

from apps.audit.models import AuditEvent
from apps.contacts.models import Contact
from apps.suppression.models import Suppression
from apps.suppression.services import is_suppressed, suppress

from .conftest import csv_file


def make_campaign(client, *numbers):
    return client.post("/v1/campaigns", {"name": "C", "contact_file": csv_file(*numbers)}, format="multipart").json()["id"]


def test_admin_suppress_is_idempotent_and_audited_once(api):
    cid = make_campaign(api("m", "Campaign Manager"), "+14155550100")
    contact = Contact.objects.get()
    admin = api("a", "Admin")
    url = f"/v1/contacts/{contact.pk}/suppress"
    r1 = admin.post(url, {"reason": "asked to stop"}, format="json")
    r2 = admin.post(url, {"reason": "again"}, format="json")
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r2.json()["reason"] == "asked to stop" and r1.json()["source"] == "manual_api"
    assert AuditEvent.objects.filter(action="suppression.add", object_id=str(contact.pk)).count() == 1
    assert admin.get(f"/v1/contacts/{contact.pk}").json()["suppression"]["reason"] == "asked to stop"


def test_manager_cannot_suppress_and_unknown_contact_404(api):
    make_campaign(api("m", "Campaign Manager"), "+14155550100")
    contact = Contact.objects.get()
    assert api("m", "Campaign Manager").post(f"/v1/contacts/{contact.pk}/suppress").status_code == 403
    assert api("a", "Admin").post("/v1/contacts/00000000-0000-0000-0000-000000000000/suppress").status_code == 404
    assert not Suppression.objects.exists()


def test_suppression_matches_by_number_across_campaigns(api):
    m = api("m", "Campaign Manager")
    make_campaign(m, "+14155550100", "+14155550101")
    make_campaign(m, "+14155550100")
    first, same_number, other = Contact.objects.order_by("created_at")[0], None, None
    for c in Contact.objects.all():
        if c.phone_number == "+14155550100" and c.pk != first.pk:
            same_number = c
        if c.phone_number == "+14155550101":
            other = c
    assert not is_suppressed(same_number)  # contact imported before the suppression exists
    suppress(first, "dnc", Suppression.Source.AGENT_IN_CALL)
    assert is_suppressed(first) and is_suppressed(same_number) and not is_suppressed(other)


def test_suppression_added_after_import_is_seen_at_check_time(api):
    make_campaign(api("m", "Campaign Manager"), "+14155550100")
    contact = Contact.objects.get()
    assert contact.status == "Pending" and not is_suppressed(contact)
    suppress(contact, "", Suppression.Source.MANUAL_API)
    contact.refresh_from_db()
    assert contact.status == "Pending" and is_suppressed(contact)  # checked at dial time, not baked into status


def test_suppressed_contact_cannot_be_deleted(api):
    make_campaign(api("m", "Campaign Manager"), "+14155550100")
    contact = Contact.objects.get()
    suppress(contact, "", Suppression.Source.MANUAL_API)
    with pytest.raises(ProtectedError):
        contact.delete()
