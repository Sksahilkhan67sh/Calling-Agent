"""Every error the API can return is the contract's ``Error`` ({code, message}); nothing leaks (OQ2-20)."""

from pathlib import Path

import pytest
import yaml
from django.test import Client
from jsonschema import Draft7Validator

from apps.core import error_codes
from apps.core.middleware import REQUEST_ID_HEADER
from tests.core.error_urls import EXCEPTIONS, SECRET_TEXT

SPEC = Path(__file__).resolve().parents[3] / "ai_calling agent" / "Backend" / "API-Specification.yaml"
ERROR_SCHEMA = yaml.safe_load(SPEC.read_text())["components"]["schemas"]["Error"]

pytestmark = pytest.mark.django_db(False)

# (name, expected status, expected code) for the urlconf's APIView exceptions
API_CASES = [
    ("validation", 400, "invalid_request"),
    ("parse", 400, "invalid_request"),
    # No authenticator offers a challenge on this view, so DRF turns 401 into 403 (the 401 case is below).
    ("authentication-failed", 403, "forbidden"),
    ("not-authenticated", 403, "forbidden"),
    ("permission-denied", 403, "forbidden"),
    ("django-permission-denied", 403, "forbidden"),
    ("django-404", 404, "not_found"),
    ("not-found", 404, "not_found"),
    ("throttled", 429, "throttled"),
    ("unknown-api-exception", 418, "error"),
    ("unhandled", 500, "internal_error"),
]


@pytest.fixture(autouse=True)
def error_urls(settings):
    settings.ROOT_URLCONF = "tests.core.error_urls"
    settings.DEBUG = False


@pytest.fixture
def client():
    return Client(raise_request_exception=False)


def assert_contract_error(response, status, code):
    assert response.status_code == status
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    Draft7Validator(ERROR_SCHEMA).validate(body)  # the contract's own schema
    assert set(body) == {"code", "message"}  # stricter than the schema: exactly these two keys
    assert body["code"] == code
    assert body["code"] in {e.code for e in error_codes.ALL}
    assert SECRET_TEXT not in response.content.decode() and "hunter2" not in response.content.decode()
    assert REQUEST_ID_HEADER in response


@pytest.mark.parametrize(("name", "status", "code"), API_CASES)
def test_each_exception_class_renders_the_contract_error(client, name, status, code):
    assert name in EXCEPTIONS
    assert_contract_error(client.get(f"/raise/{name}/"), status, code)


@pytest.mark.parametrize("name", ["authentication-failed", "not-authenticated"])
def test_authentication_errors_are_a_uniform_401_with_a_challenge(client, name):
    response = client.get(f"/challenge/{name}/")
    assert_contract_error(response, 401, "invalid_credentials")
    assert "WWW-Authenticate" in response or "Www-Authenticate" in response.headers


def test_method_not_allowed(client):
    assert_contract_error(client.put("/raise/unhandled/"), 405, "method_not_allowed")


def test_not_acceptable(client):
    assert_contract_error(
        client.get("/raise/unhandled/", HTTP_ACCEPT="application/xml"), 406, "not_acceptable"
    )


def test_unsupported_media_type(client):
    response = client.post("/raise/unhandled/", data="x", content_type="text/plain")
    assert_contract_error(response, 415, "unsupported_media_type")


def test_throttled_keeps_retry_after(client):
    response = client.get("/raise/throttled/")
    assert response["Retry-After"] == "30"
    assert_contract_error(response, 429, "throttled")


def test_unrouted_path_is_a_json_404(client):
    assert_contract_error(client.get("/no/such/path/"), 404, "not_found")


def test_django_level_errors_are_json(client):
    assert_contract_error(client.get("/plain/404/"), 404, "not_found")
    assert_contract_error(client.get("/plain/403/"), 403, "forbidden")
    assert_contract_error(client.get("/plain/400/"), 400, "invalid_request")
    assert_contract_error(client.get("/plain/500/"), 500, "internal_error")


def test_disallowed_host_is_a_json_400(client, settings):
    settings.ALLOWED_HOSTS = ["testserver"]
    assert_contract_error(client.get("/plain/404/", HTTP_HOST="evil.example"), 400, "invalid_request")


def test_csrf_failure_view_is_json():
    csrf_client = Client(enforce_csrf_checks=True, raise_request_exception=False)
    assert_contract_error(csrf_client.post("/plain/csrf/"), 403, "csrf_failed")


def test_no_debug_information_in_any_error_with_debug_off(client, settings):
    settings.DEBUG = False
    for name in EXCEPTIONS:
        text = client.get(f"/raise/{name}/").content.decode()
        for marker in ("Traceback", "SELECT", "SECRET_KEY", "settings", "RuntimeError", 'File "'):
            assert marker not in text


def test_registry_is_consistent():
    codes = [e.code for e in error_codes.ALL]
    assert len(codes) == len(set(codes))  # codes are unique and stable
    assert all(e.message and e.message.endswith(".") for e in error_codes.ALL)
    assert error_codes.for_status(599) is error_codes.REQUEST_FAILED
    assert error_codes.for_status(404) is error_codes.NOT_FOUND
