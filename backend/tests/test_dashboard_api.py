import boto3
import pytest
import responses
from moto import mock_aws

from apps.audit.models import AuditEvent

from .test_calling_engine import attempts, contact, dial, hook, run_url  # noqa: F401
from .test_recovery_analysis import REC, TRN, body


@pytest.fixture
def done(contact, api):
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="test-recordings")
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            rsps.post("https://dograh.test/api/v1/public/agent/workflow/6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d", json={"workflow_run_id": "r1"})
            from apps.dialer.tasks import dispatch_due
            dispatch_due()
            a = attempts(contact)[0]
            rsps.get(run_url("r1"), json=body(a, recording_consent="granted"))
            rsps.get(TRN, body="agent: hello")
            rsps.get(REC, body=b"audio")
            hook(a, "r1")
        yield a


def test_attempt_endpoints_audit_access_and_sign_recording(done, api):
    admin = api("admin", "Admin")
    assert admin.get(f"/v1/call-attempts/{done.pk}").json()["state"] == "EndedNormally"
    assert admin.get(f"/v1/call-attempts/{done.pk}/transcript").json()["content"] == "agent: hello"
    rec = admin.get(f"/v1/call-attempts/{done.pk}/recording").json()
    assert f"recordings/{done.pk}" in rec["url"] and rec["duration_seconds"] == 31
    assert admin.get(f"/v1/call-attempts/{done.pk}/disconnect-events").json() == []
    assert {"transcript.access", "recording.access"} <= set(AuditEvent.objects.values_list("action", flat=True))


def test_sales_sees_final_output_but_no_raw_artifacts(done, api, contact):
    sales = api("s1", "Sales/Follow-up")
    fo = sales.get(f"/v1/contacts/{contact.pk}/final-output").json()
    assert fo["lead_score_summary"]["temperature_tag"] == "Hot" and "content" not in str(fo["transcript"]) and "url" not in fo["recording"]
    for path in ("", "/transcript", "/recording", "/disconnect-events"):
        assert sales.get(f"/v1/call-attempts/{done.pk}{path}").status_code == 403


def test_manager_scope_is_own_campaigns_and_missing_artifacts_404(done, api, contact):
    assert api("other", "Campaign Manager").get(f"/v1/call-attempts/{done.pk}").status_code == 404
    assert api("other", "Campaign Manager").get(f"/v1/dashboard/campaigns/{contact.campaign_id}/analytics").status_code == 404
    assert api("admin", "Admin").get(f"/v1/contacts/{contact.pk}/final-output").status_code == 200


def test_analytics_and_unfinished_final_output(done, api, contact):
    r = api("admin", "Admin").get(f"/v1/dashboard/campaigns/{contact.campaign_id}/analytics").json()
    assert r["status_counts"] == {"Completed": 1} and r["temperature_distribution"]["Hot"] == 1
    assert r["disconnect_rate"] == 0 and r["reconnect_success_rate"] is None and r["average_lead_score"] >= 80


def test_contact_detail_includes_attempts_and_final_output(done, api, contact):
    d = api("s1", "Sales/Follow-up").get(f"/v1/contacts/{contact.pk}").json()
    assert d["attempts"][0]["state"] == "EndedNormally" and d["final_output"]["lead_score_summary"]["lead_score"] >= 80
