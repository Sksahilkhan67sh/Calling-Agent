import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from openpyxl import Workbook

from apps.audit.models import AuditEvent
from apps.campaigns.models import Campaign
from apps.contacts.models import Contact
from apps.core.crypto import phone_hmac

from .conftest import csv_file

URL = "/v1/campaigns"


def create(client, *numbers, **extra):
    return client.post(URL, {"name": "Q4", "contact_file": csv_file(*numbers), **extra}, format="multipart")


def test_import_validates_dedupes_and_sets_pending(api):
    r = create(api("m1", "Campaign Manager"), "+14155550100", "+14155550100", "not-a-number", "+1 415 555 0101", "4155550102", "+999")
    assert r.status_code == 201 and r.json()["contact_count"] == 2 and r.json()["status"] == "draft"
    assert set(Contact.objects.values_list("status", flat=True)) == {"Pending"}


def test_phone_numbers_are_encrypted_at_rest(api):
    create(api("m1", "Campaign Manager"), "+14155550100")
    with connection.cursor() as c:
        c.execute("select phone_encrypted, phone_hmac from contacts_contact")
        enc, h = c.fetchone()
    assert b"4155550100" not in bytes(enc) and bytes(h) == phone_hmac("+14155550100")


def test_xlsx_import(api):
    wb = Workbook()
    wb.active.append(["Name", "Phone"])
    wb.active.append(["a", "+14155550100"])
    buf = io.BytesIO()
    wb.save(buf)
    f = SimpleUploadedFile("c.xlsx", buf.getvalue())
    r = api("m1", "Campaign Manager").post(URL, {"name": "X", "contact_file": f}, format="multipart")
    assert r.status_code == 201 and r.json()["contact_count"] == 1


@pytest.mark.parametrize("file", [
    csv_file(),
    csv_file("garbage", "123"),
    csv_file("+14155550100", header="name"),
    SimpleUploadedFile("c.txt", b"phone_number\n+14155550100"),
    SimpleUploadedFile("c.csv", b"\xff\xfe\x00bad"),
    SimpleUploadedFile("c.xlsx", b"not a zip"),
])
def test_bad_import_creates_no_campaign(api, file):
    r = api("m1", "Campaign Manager").post(URL, {"name": "X", "contact_file": file}, format="multipart")
    assert r.status_code == 400 and not Campaign.objects.exists()


def test_oversized_import_rejected(api, settings):
    settings.CONTACT_IMPORT_MAX_BYTES = 10
    assert create(api("m1", "Campaign Manager"), "+14155550100", "+14155550101").status_code == 400


def test_duplicate_number_in_campaign_is_a_db_error(api):
    create(api("m1", "Campaign Manager"), "+14155550100")
    c = Contact.objects.get()
    with pytest.raises(IntegrityError):
        Contact.objects.create(campaign=c.campaign, phone_encrypted=b"x", phone_hmac=c.phone_hmac)


def test_manager_sees_only_own_campaigns(api):
    a, b, admin = api("a", "Campaign Manager"), api("b", "Campaign Manager"), api("adm", "Admin")
    cid = create(a, "+14155550100").json()["id"]
    assert [c["id"] for c in a.get(URL).json()] == [cid]
    assert b.get(URL).json() == []
    for url in (f"{URL}/{cid}", f"{URL}/{cid}/retry-policy", f"{URL}/{cid}/agent-config", f"{URL}/{cid}/contacts"):
        assert b.get(url).status_code == 404 and admin.get(url).status_code == 200
    assert b.patch(f"{URL}/{cid}", {"status": "active"}, format="json").status_code == 404


def test_sales_reads_campaigns_but_cannot_write_or_see_config(api):
    cid = create(api("m", "Campaign Manager"), "+14155550100").json()["id"]
    sales = api("s", "Sales/Follow-up")
    assert [c["id"] for c in sales.get(URL).json()] == [cid]
    detail = sales.get(f"{URL}/{cid}").json()
    assert set(detail) == {"id", "name", "status", "contact_count", "created_at"}
    assert sales.post(URL).status_code == 403
    assert sales.patch(f"{URL}/{cid}", {"status": "active"}, format="json").status_code == 403
    for part in ("retry-policy", "agent-config"):
        assert sales.get(f"{URL}/{cid}/{part}").status_code == 403
    assert sales.post(f"{URL}/{cid}/sync-workflow").status_code == 403
    assert sales.get(f"{URL}/{cid}/contacts").json()["total"] == 1
    contact = Contact.objects.get()
    assert sales.get(f"/v1/contacts/{contact.pk}").json()["phone_number"] == "+14155550100"
    assert sales.post(f"/v1/contacts/{contact.pk}/suppress").status_code == 403


def test_user_without_role_is_denied(api):
    assert api("nobody", None).get(URL).status_code == 403


def test_status_transitions(api):
    m = api("m", "Campaign Manager")
    cid = create(m, "+14155550100").json()["id"]
    assert m.patch(f"{URL}/{cid}", {"status": "paused"}, format="json").status_code == 400
    assert m.patch(f"{URL}/{cid}", {"status": "active"}, format="json").json()["status"] == "active"
    assert m.patch(f"{URL}/{cid}", {"status": "completed"}, format="json").status_code == 200
    assert m.patch(f"{URL}/{cid}", {"status": "active"}, format="json").status_code == 400
    assert m.patch(f"{URL}/{cid}", {"status": "bogus"}, format="json").status_code == 400
    assert m.get(f"{URL}?status=bogus").status_code == 400 and m.get(f"{URL}?status=completed").json()[0]["id"] == cid


def test_defaults_match_spec(api):
    cid = create(api("m", "Campaign Manager"), "+14155550100").json()["id"]
    rp = api("a", "Admin").get(f"{URL}/{cid}/retry-policy").json()
    assert rp["max_retries"] == 2 and rp["retry_spacing_seconds"] == [30, 600]
    assert rp["window_start"] == "10:00:00" and rp["window_end"] == "18:00:00"
    assert rp["never_connected_rules"]["invalid_number"] is False and rp["mid_call_rules"]["customer_hangup"] is False


def test_only_admin_writes_retry_policy_and_it_is_audited(api):
    cid = create(api("m", "Campaign Manager"), "+14155550100").json()["id"]
    body = {"max_retries": 1, "retry_spacing_seconds": [60], "mid_call_rules": {"unknown": False}}
    assert api("m2", "Campaign Manager").put(f"{URL}/{cid}/retry-policy", body, format="json").status_code == 403
    assert api("m", "Campaign Manager").put(f"{URL}/{cid}/retry-policy", body, format="json").status_code == 403
    r = api("a", "Admin").put(f"{URL}/{cid}/retry-policy", body, format="json")
    assert r.status_code == 200 and r.json()["mid_call_rules"]["unknown"] is False and r.json()["mid_call_rules"]["ai_error"] is True
    e = AuditEvent.objects.get(action="retry_policy.update")
    assert e.object_id == cid and e.actor == "a" and e.before["max_retries"] == 2 and e.after["max_retries"] == 1


@pytest.mark.parametrize("body", [
    {"max_retries": -1},
    {"max_retries": 3},  # spacing still has 2 values
    {"retry_spacing_seconds": [30]},
    {"max_retries": 1, "retry_spacing_seconds": [-5]},
    {"never_connected_rules": {"technical_issue": True}},
    {"mid_call_rules": {"nope": True}},
    {"window_start": "18:00:00", "window_end": "10:00:00"},
])
def test_invalid_retry_policy_is_rejected_and_unchanged(api, body):
    cid = create(api("m", "Campaign Manager"), "+14155550100").json()["id"]
    admin = api("a", "Admin")
    assert admin.put(f"{URL}/{cid}/retry-policy", body, format="json").status_code == 400
    assert admin.get(f"{URL}/{cid}/retry-policy").json()["max_retries"] == 2
    assert not AuditEvent.objects.filter(action="retry_policy.update").exists()


def test_agent_config_admin_only_and_audited(api):
    cid = create(api("m", "Campaign Manager"), "+14155550100").json()["id"]
    body = {"persona_tone": "warm", "script_skeleton": ["hi", "pitch"], "required_entity_fields": ["objection"]}
    assert api("m", "Campaign Manager").put(f"{URL}/{cid}/agent-config", body, format="json").status_code == 403
    admin = api("a", "Admin")
    assert admin.put(f"{URL}/{cid}/agent-config", {"required_entity_fields": ["bogus"]}, format="json").status_code == 400
    r = admin.put(f"{URL}/{cid}/agent-config", body, format="json")
    assert r.status_code == 200 and r.json()["script_skeleton"] == ["hi", "pitch"] and r.json()["prompt_template_version"] == "v1"
    assert AuditEvent.objects.filter(action="agent_config.update", object_id=cid).count() == 1


def test_create_with_config_requires_admin_and_validates(api):
    cfg = {"retry_policy": '{"max_retries": 1, "retry_spacing_seconds": [45]}', "agent_config": '{"persona_tone": "calm"}'}
    assert create(api("m", "Campaign Manager"), "+14155550100", **cfg).status_code == 403
    assert not Campaign.objects.exists()
    bad = create(api("a", "Admin"), "+14155550100", retry_policy='{"max_retries": 5}')
    assert bad.status_code == 400 and not Campaign.objects.exists()
    ok = create(api("a", "Admin"), "+14155550100", **cfg)
    assert ok.status_code == 201
    cid = ok.json()["id"]
    assert api("a", "Admin").get(f"{URL}/{cid}/retry-policy").json()["retry_spacing_seconds"] == [45]
    assert api("a", "Admin").get(f"{URL}/{cid}/agent-config").json()["persona_tone"] == "calm"


def test_contact_list_paginates_and_filters(api):
    m = api("m", "Campaign Manager")
    cid = create(m, *[f"+1415555{i:04d}" for i in range(120)]).json()["id"]
    r = m.get(f"{URL}/{cid}/contacts?page=3&page_size=50").json()
    assert (r["total"], r["page"], len(r["items"])) == (120, 3, 20)
    Contact.objects.filter(pk=Contact.objects.first().pk).update(status="Closed")
    assert m.get(f"{URL}/{cid}/contacts?status=Closed").json()["total"] == 1
    assert m.get(f"{URL}/{cid}/contacts?status=bogus").status_code == 400
