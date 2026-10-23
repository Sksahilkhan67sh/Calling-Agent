import io
import json

import pytest
import requests
import responses

from apps.voice_runtime.client import DialOutcomeUnknown, DograhClient, DograhError, StartCallRequest

BASE = "https://dograh.test"
WF = "6f1c2b1e-6f3a-4c55-8f55-0d6d0d6d0d6d"
TRIGGER = f"{BASE}/api/v1/public/agent/workflow/{WF}"
ART = "https://artifacts.dograh.test/rec.mp3"


def req(**kw):
    return StartCallRequest(workflow_uuid=WF, phone_number="+14155550100", attempt_id="a1", campaign_id="c1",
                            contact_ref="ref1", **kw)


@responses.activate
def test_start_call_sends_context_and_stores_run_id():
    responses.post(TRIGGER, json={"workflow_run_id": 77})
    assert DograhClient().start_call(req(prompt_vars={"attempt_id": "forged", "name": "x"})).run_id == "77"
    sent = responses.calls[0].request
    body = json.loads(sent.body)
    assert sent.headers["X-API-Key"] == "test-only-dograh-key" and sent.req_kwargs["timeout"] == 5
    assert body["initial_context"] == {"attempt_id": "a1", "campaign_id": "c1", "contact_ref": "ref1", "name": "x"}
    assert "model_overrides" not in body


@responses.activate
def test_model_override_and_default(settings):
    responses.post(TRIGGER, json={"workflow_run_id": 1})
    DograhClient().start_call(req(model_config_uuid="m-1"))
    assert json.loads(responses.calls[0].request.body)["model_overrides"]["model_configuration_uuid"] == "m-1"
    settings.DOGRAH_DEFAULT_MODEL_CONFIG_UUID = "m-default"
    DograhClient().start_call(req())
    assert json.loads(responses.calls[1].request.body)["model_overrides"]["model_configuration_uuid"] == "m-default"


def test_phone_number_not_in_repr():
    assert "4155550100" not in repr(req())


@pytest.mark.parametrize("outcome", [
    {"body": requests.exceptions.ReadTimeout()}, {"body": requests.exceptions.ConnectionError()},
    {"status": 502}, {"status": 200, "json": {}},
])
@responses.activate
def test_trigger_with_unknown_outcome_is_never_retried(outcome):
    responses.post(TRIGGER, **outcome)
    with pytest.raises(DialOutcomeUnknown):
        DograhClient().start_call(req())
    assert len(responses.calls) == 1


@responses.activate
def test_trigger_client_error_is_definite_failure():
    responses.post(TRIGGER, status=422, json={"detail": "+14155550100 invalid"})
    with pytest.raises(DograhError) as e:
        DograhClient().start_call(req())
    assert not isinstance(e.value, DialOutcomeUnknown) and "4155550100" not in str(e.value)


@responses.activate
def test_get_run_parses_terminal_and_running():
    responses.get(f"{BASE}/api/v1/runs/9", json={
        "status": "completed", "initial_context": {"attempt_id": "a1"}, "gathered_context": {"call_status": "ok"},
        "cost_info": {"call_duration_seconds": 42}, "recording_url": ART})
    run = DograhClient().get_run("9")
    assert run.terminal and run.initial_context["attempt_id"] == "a1" and run.duration_seconds == 42
    assert "rec.mp3" not in repr(run)
    responses.get(f"{BASE}/api/v1/runs/10", json={"status": "in-progress", "initial_context": {}})
    assert not DograhClient().get_run("10").terminal


@pytest.mark.parametrize("kw", [{"json": {"status": "completed"}}, {"body": "not json"}, {"status": 404},
                                {"json": ["x"]}, {"body": requests.exceptions.ConnectTimeout()}])
@responses.activate
def test_get_run_bad_responses_raise(kw):
    responses.get(f"{BASE}/api/v1/runs/9", **kw)
    with pytest.raises(DograhError):
        DograhClient().get_run("9")


@responses.activate
def test_download_artifact_streams_without_api_key():
    responses.get(ART, body=b"audio")
    buf = io.BytesIO()
    DograhClient().download_artifact(ART, buf)
    assert buf.getvalue() == b"audio" and "X-API-Key" not in responses.calls[0].request.headers


@pytest.mark.parametrize("url", ["https://evil.test/rec.mp3", "http://artifacts.dograh.test/rec.mp3",
                                 "https://artifacts.dograh.test.evil.test/x", "file:///etc/passwd"])
@responses.activate
def test_download_rejects_unlisted_hosts_before_any_request(url):
    with pytest.raises(DograhError):
        DograhClient().download_artifact(url, io.BytesIO())
    assert not responses.calls


@responses.activate
def test_download_enforces_size_limit_and_ignores_redirects():
    responses.get(ART, body=b"x" * 2048)
    with pytest.raises(DograhError, match="limit"):
        DograhClient().download_artifact(ART, io.BytesIO())
    responses.replace(responses.GET, ART, status=302, headers={"Location": "https://evil.test/x"})
    with pytest.raises(DograhError, match="302"):
        DograhClient().download_artifact(ART, io.BytesIO())
    assert len(responses.calls) == 2


@responses.activate
def test_download_enforces_deadline(settings):
    settings.DOGRAH_ARTIFACT_DEADLINE_SECONDS = -1
    responses.get(ART, body=b"x")
    with pytest.raises(DograhError, match="time"):
        DograhClient().download_artifact(ART, io.BytesIO())
