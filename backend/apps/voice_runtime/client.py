import time
import uuid
from dataclasses import dataclass, field
from typing import BinaryIO, Protocol
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings

TERMINAL_STATUSES = {"completed", "busy", "no-answer", "canceled", "failed", "error"}


class DograhError(Exception):
    """Definite failure; messages never carry URLs, bodies or phone numbers."""


class DialOutcomeUnknown(DograhError):
    """Trigger call may or may not have placed a call; resolve via reconciler, never redial."""


@dataclass
class StartCallRequest:
    workflow_uuid: str
    phone_number: str = field(repr=False)
    attempt_id: str
    campaign_id: str
    contact_ref: str
    prompt_vars: dict = field(default_factory=dict)
    model_config_uuid: str | None = None


@dataclass
class StartedCall:
    run_id: str


@dataclass
class RunResult:
    run_id: str
    status: str
    initial_context: dict
    gathered_context: dict
    duration_seconds: float | None
    recording_url: str | None = field(default=None, repr=False)
    transcript_url: str | None = field(default=None, repr=False)

    @property
    def terminal(self):
        return self.status in TERMINAL_STATUSES


class VoiceRuntime(Protocol):
    def start_call(self, req: StartCallRequest) -> StartedCall: ...
    def get_run(self, run_id: str) -> RunResult: ...
    def download_artifact(self, url: str, dest: BinaryIO) -> None: ...
    def push_workflow(self, workflow_uuid: str | None, definition: dict) -> str: ...
    def publish_workflow(self, workflow_uuid: str) -> None: ...


def _send(method, path, **kw):
    return requests.request(
        method, settings.DOGRAH_BASE_URL.rstrip("/") + path, headers={"X-API-Key": settings.DOGRAH_API_KEY},
        timeout=settings.DOGRAH_REQUEST_TIMEOUT_SECONDS, allow_redirects=False, **kw)


def _json(r):
    if not 200 <= r.status_code < 300:
        raise DograhError(f"Dograh returned HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise DograhError("Dograh returned a non-JSON body") from None


class DograhClient:
    # No method here retries: a retried trigger could place a second call.
    def start_call(self, req):
        body = {"phone_number": req.phone_number,
                "initial_context": {**req.prompt_vars, "attempt_id": req.attempt_id,
                                    "campaign_id": req.campaign_id, "contact_ref": req.contact_ref}}
        if model := req.model_config_uuid or settings.DOGRAH_DEFAULT_MODEL_CONFIG_UUID:
            body["model_overrides"] = {"model_configuration_uuid": model}  # [verify] body shape not in docs
        try:
            r = _send("POST", f"/api/v1/public/agent/workflow/{quote(req.workflow_uuid, safe='')}", json=body)
        except requests.RequestException:
            raise DialOutcomeUnknown("No response from Dograh trigger call") from None
        if r.status_code >= 500:
            raise DialOutcomeUnknown(f"Dograh trigger returned HTTP {r.status_code}")
        try:
            return StartedCall(run_id=str(_json(r)["workflow_run_id"]))
        except (KeyError, TypeError):
            raise DialOutcomeUnknown("Dograh trigger response had no workflow_run_id") from None

    def get_run(self, run_id):
        try:
            d = _json(_send("GET", f"{settings.DOGRAH_RUN_PATH}/{quote(run_id, safe='')}"))
            return RunResult(
                run_id=run_id, status=d["status"], initial_context=d["initial_context"] or {},
                gathered_context=d.get("gathered_context") or {},
                duration_seconds=(d.get("cost_info") or {}).get("call_duration_seconds"),
                recording_url=d.get("recording_url"), transcript_url=d.get("transcript_url"))
        except requests.RequestException:
            raise DograhError("No response from Dograh run lookup") from None
        except (KeyError, TypeError, AttributeError):
            raise DograhError("Unexpected Dograh run payload") from None

    def push_workflow(self, workflow_uuid, definition):
        try:
            if workflow_uuid is None:
                created = _json(_send("POST", settings.DOGRAH_WORKFLOW_PATH, json=definition))
                return str(uuid.UUID(str(created["uuid"])))  # [verify] response key not in docs
            _json(_send("PUT", f"{settings.DOGRAH_WORKFLOW_PATH}/{workflow_uuid}", json=definition))
            return str(workflow_uuid)
        except requests.RequestException:
            raise DograhError("No response from Dograh workflow push") from None
        except (KeyError, TypeError, ValueError):
            raise DograhError("Unexpected Dograh workflow response") from None

    def publish_workflow(self, workflow_uuid):
        try:
            _json(_send("POST", f"{settings.DOGRAH_WORKFLOW_PATH}/{workflow_uuid}/publish"))
        except requests.RequestException:
            raise DograhError("No response from Dograh workflow publish") from None

    def download_artifact(self, url, dest):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in settings.DOGRAH_ALLOWED_ARTIFACT_HOSTS:
            raise DograhError("Artifact host is not allowed")
        limit, deadline = settings.DOGRAH_MAX_ARTIFACT_BYTES, time.monotonic() + settings.DOGRAH_ARTIFACT_DEADLINE_SECONDS
        try:
            # The URL is a bearer credential: no API key sent, no redirects followed.
            with requests.get(url, stream=True, allow_redirects=False,
                              timeout=settings.DOGRAH_REQUEST_TIMEOUT_SECONDS) as r:
                if r.status_code != 200:
                    raise DograhError(f"Artifact download returned HTTP {r.status_code}")
                size = 0
                for chunk in r.iter_content(65536):
                    size += len(chunk)
                    if size > limit or time.monotonic() > deadline:
                        raise DograhError("Artifact exceeded size or time limit")
                    dest.write(chunk)
        except requests.RequestException:
            raise DograhError("Artifact download failed") from None
