import re
from datetime import timedelta
from unittest import mock

import boto3
import pytest
import responses
from django.core.cache import cache
from django.urls import get_resolver
from moto import mock_aws
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone

from apps.calls.models import CallAttempt, DisconnectEvent, RecordingRef, Transcript
from apps.contacts.models import Contact
from apps.core.permissions import RolePermission
from apps.dialer.tasks import dispatch_due
from apps.recovery.models import WorkingMemorySnapshot
from apps.recovery.tasks import sweep_retention
from apps.suppression.models import Suppression
from apps.suppression.services import suppress
from apps.webhooks.models import WebhookReceipt

from .test_calling_engine import HOOK, SECRET, TRIGGER, attempts, contact, dial, hook, run_url, triggers  # noqa: F401
from .test_rbac import _views
from .test_recovery_analysis import REC, TRN, body

ROLES = ("Admin", "Campaign Manager", "Sales/Follow-up")


def test_full_role_by_endpoint_matrix(make_user):
    checked = 0
    for view in _views(get_resolver().url_patterns):
        for method, allowed in getattr(view, "roles", {}).items():
            for role in ROLES:
                req = type("R", (), {"method": method, "user": make_user(f"{view.__name__}{method}{role[:3]}", role)})()
                assert RolePermission().has_permission(req, view) is (role in allowed), (view.__name__, method, role)
                checked += 1
    assert checked > 30


def test_campaign_manager_cannot_write_policy_or_agent_config(api, contact):
    mgr = api("m", "Campaign Manager")
    for part in ("retry-policy", "agent-config"):
        assert mgr.put(f"/v1/campaigns/{contact.campaign_id}/{part}", {}, format="json").status_code == 403


def test_unauthenticated_requests_never_reach_data(db):
    paths = ["/v1/campaigns", "/v1/dashboard/campaigns/6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d/analytics",
             "/v1/call-attempts/6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d/recording"]
    assert {APIClient().get(p).status_code for p in paths} <= {401, 403}


# --- Test Plan §4: snapshot must be durable before any retry decision --------------------------

@pytest.mark.parametrize("n", range(5))
@responses.activate
def test_snapshot_failure_never_fails_open_into_a_retry(contact, n):
    dial("r1")
    a = attempts(contact)[0]
    responses.get(run_url("r1"), json=body(a, "dropped"))
    responses.get(TRN, body="t")
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="test-recordings")
        with mock.patch("apps.recovery.services.save_snapshot", side_effect=RuntimeError("write failed")), pytest.raises(RuntimeError):
            hook(a, "r1")
    a.refresh_from_db()
    assert a.state == "Initiated" and Contact.objects.get(pk=contact.pk).status == "Dialing"
    assert len(attempts(contact)) == 1 and not DisconnectEvent.objects.exists() and not WorkingMemorySnapshot.objects.exists()


# --- Test Plan §5: suppression bypass ---------------------------------------------------------

@responses.activate
def test_retry_queued_before_suppression_never_dials(contact):
    responses.post(TRIGGER, status=422)
    dispatch_due()
    assert Contact.objects.get(pk=contact.pk).status == "RetryScheduled"
    CallAttempt.objects.filter(started_at__isnull=True).update(next_dispatch_at=timezone.now())
    suppress(contact, "asked", "manual_api")
    dispatch_due()
    assert len(triggers()) == 1 and Contact.objects.get(pk=contact.pk).status == "Closed"


@responses.activate
def test_in_call_and_manual_suppression_share_one_table_and_are_honoured_equally(contact, api):
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="test-recordings")
        dial("r1")
        a = attempts(contact)[0]
        responses.get(run_url("r1"), json=body(a, requires_suppression=True))
        responses.get(TRN, body="t")
        hook(a, "r1")
    assert Suppression.objects.get(contact=contact).source == "agent_in_call"
    other = Contact.objects.create(campaign=contact.campaign, phone_encrypted=b"x", phone_hmac=b"y")
    r = api("admin", "Admin").post(f"/v1/contacts/{other.pk}/suppress", {"reason": "r"}, format="json")
    assert r.status_code == 201 and set(Suppression.objects.values_list("source", flat=True)) == {"agent_in_call", "manual_api"}


# --- webhook flood (Test Plan §10, in-process) -------------------------------------------------

@responses.activate
def test_legitimate_flood_under_limit_is_not_dropped(contact):
    dial("r1")
    a = attempts(contact)[0]
    responses.get(re.compile(r".*/api/v1/runs/f\d+"), json={"status": "in-progress", "initial_context": {}})
    c = APIClient()
    codes = {c.post(HOOK, {"attempt_id": str(a.pk), "run_id": f"f{i}"}, format="json", **SECRET).status_code for i in range(150)}
    assert codes == {200} and WebhookReceipt.objects.count() == 150


def test_flood_above_limit_is_throttled(monkeypatch, db):
    cache.clear()
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "webhook", "3/min")
    c = APIClient()
    codes = [c.post(HOOK, {"attempt_id": "x", "run_id": "y"}, format="json", **SECRET).status_code for _ in range(5)]
    cache.clear()
    assert codes[:3] == [422] * 3 and codes[3:] == [429, 429]


# --- retention ---------------------------------------------------------------------------------

@responses.activate
def test_retention_deletes_expired_artifacts_but_never_suppression(contact):
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="test-recordings")
        dial("r1")
        a = attempts(contact)[0]
        responses.get(run_url("r1"), json=body(a, recording_consent="granted"))
        responses.get(TRN, body="t")
        responses.get(REC, body=b"audio")
        hook(a, "r1")
        suppress(contact, "asked", "manual_api")
        sweep_retention()
        assert RecordingRef.objects.exists() and Transcript.objects.exists()  # still inside the window
        CallAttempt.objects.update(ended_at=timezone.now() - timedelta(days=31))
        WorkingMemorySnapshot.objects.update(snapshotted_at=timezone.now() - timedelta(days=31))
        sweep_retention()
        assert not RecordingRef.objects.exists() and not Transcript.objects.exists() and not WorkingMemorySnapshot.objects.exists()
        assert s3.list_objects_v2(Bucket="test-recordings")["KeyCount"] == 0 and Suppression.objects.count() == 1


@responses.activate
def test_retention_keeps_row_when_object_delete_fails(contact):
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="test-recordings")
        dial("r1")
        a = attempts(contact)[0]
        responses.get(run_url("r1"), json=body(a, recording_consent="granted"))
        responses.get(TRN, body="t")
        responses.get(REC, body=b"audio")
        hook(a, "r1")
        CallAttempt.objects.update(ended_at=timezone.now() - timedelta(days=31))
        from botocore.exceptions import ClientError

        with mock.patch("apps.recovery.tasks.s3") as fake:
            fake.return_value.delete_object.side_effect = ClientError({"Error": {"Code": "500"}}, "DeleteObject")
            sweep_retention()
        assert RecordingRef.objects.exists()
