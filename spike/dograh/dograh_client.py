"""Minimal Dograh API client for the spike. Bounded timeouts, no retries, never logs headers."""
import json
import os
import time
from dataclasses import dataclass

import httpx

import call_guard

PUBLIC = "/api/v1/public/agent/workflow/{uuid}"


@dataclass
class Result:
    status: int
    body: object
    elapsed_s: float
    error: str = ""


class DograhClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 15.0, transport=None):
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers={"X-API-Key": api_key},
                                  timeout=timeout_s, follow_redirects=False, transport=transport)

    @classmethod
    def from_env(cls, **kw):
        return cls(os.environ["DOGRAH_BASE_URL"], os.environ["DOGRAH_API_KEY"], **kw)

    def _call(self, method, path, timeout_s=None, **kw) -> Result:
        start = time.monotonic()
        extra = {"timeout": timeout_s} if timeout_s else {}
        try:
            r = self._http.request(method, path, **extra, **kw)
        except httpx.HTTPError as exc:  # timeout / connect error: outcome may be unknown
            return Result(0, None, time.monotonic() - start, error=type(exc).__name__)
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return Result(r.status_code, body, time.monotonic() - start)

    def start_call(self, workflow_uuid, phone_number, initial_context, purpose,
                   timeout_s=None, **extra_body) -> Result:
        """Guarded: refuses unless LIVE_TESTING=yes, number owned, cap not reached. Never retried."""
        call_guard.authorize(phone_number, purpose)
        body = {"phone_number": phone_number, "initial_context": initial_context, **extra_body}
        return self._call("POST", PUBLIC.format(uuid=workflow_uuid), timeout_s, json=body)

    def get_run(self, workflow_id, run_id) -> Result:
        return self._call("GET", f"/api/v1/workflow/{workflow_id}/runs/{run_id}")

    def list_runs(self, workflow_id, page=1, limit=100, filters=None, sort_order="desc") -> Result:
        params = {"page": page, "limit": limit, "sort_order": sort_order}
        if filters is not None:
            params["filters"] = json.dumps(filters)
        return self._call("GET", f"/api/v1/workflow/{workflow_id}/runs", params=params)

    def usage_runs(self, start_date=None, end_date=None, page=1, limit=100, filters=None) -> Result:
        params = {"page": page, "limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if filters is not None:
            params["filters"] = json.dumps(filters)
        return self._call("GET", "/api/v1/organizations/usage/runs", params=params)

    def list_agents(self) -> Result:
        return self._call("GET", "/api/v1/workflow/fetch")

    def get_agent(self, workflow_id) -> Result:
        return self._call("GET", f"/api/v1/workflow/fetch/{workflow_id}")

    def create_agent(self, name, workflow_definition) -> Result:
        return self._call("POST", "/api/v1/workflow/create/definition",
                          json={"name": name, "workflow_definition": workflow_definition})

    def update_agent(self, workflow_id, **fields) -> Result:
        return self._call("PUT", f"/api/v1/workflow/{workflow_id}", json=fields)

    def validate_agent(self, workflow_id) -> Result:
        return self._call("POST", f"/api/v1/workflow/{workflow_id}/validate")
