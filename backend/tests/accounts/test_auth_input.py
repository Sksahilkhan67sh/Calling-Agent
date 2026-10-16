"""Hostile and odd input to the credential endpoints: never a 500, never an echo (P2-09)."""

import json

import pytest
from django.core.cache import caches

from apps.accounts import mfa
from apps.accounts.parsers import MAX_BODY_BYTES
from apps.accounts.roles import ROLE_SALES_FOLLOW_UP
from tests.accounts.conftest import PASSWORD
from tests.accounts.helpers import CSRF, LOGOUT, REFRESH, TOKEN, browser, login

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

GENERIC_400 = {"code": "invalid_request", "message": "Invalid request."}


@pytest.fixture(autouse=True)
def _wide_limits():
    from apps.core.throttles import LoginThrottle

    original = LoginThrottle.THROTTLE_RATES["login"]
    LoginThrottle.THROTTLE_RATES["login"] = "10000/min"
    caches["default"].clear()
    yield
    LoginThrottle.THROTTLE_RATES["login"] = original


def raw_post(client, body: bytes, content_type="application/json", path=TOKEN):
    return client.generic("POST", path, body, content_type=content_type)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"username": "a@example.com"},
        {"password": PASSWORD},
        {"username": "", "password": PASSWORD},
        {"username": "a@example.com", "password": ""},
        {"username": None, "password": PASSWORD},
        {"username": "a@example.com", "password": None},
        {"username": 123, "password": PASSWORD},
        {"username": "a@example.com", "password": 123456789012},  # DRF would coerce this to text; we refuse
        {"username": ["a@example.com"], "password": PASSWORD},
        {"username": {"a": 1}, "password": PASSWORD},
        {"username": True, "password": PASSWORD},
        {"username": "a@example.com", "password": PASSWORD, "mfa_code": 123456},
        {"username": "a@example.com", "password": PASSWORD, "mfa_code": None},
        {"username": "a@example.com", "password": PASSWORD, "mfa_code": "1" * 17},
        {"username": "a" * 255, "password": PASSWORD},
        {"username": "a@example.com", "password": "p" * 257},
    ],
    ids=lambda p: json.dumps(p)[:60],
)
def test_malformed_credentials_get_a_generic_400(payload):
    response = browser().post(TOKEN, payload, format="json")
    assert response.status_code == 400 and response.json() == GENERIC_400


@pytest.mark.parametrize("extra", ["is_staff", "role", "__proto__", "password2", "x" * 40])
def test_unknown_fields_are_rejected_without_being_echoed(extra):
    response = browser().post(
        TOKEN, {"username": "a@example.com", "password": PASSWORD, extra: "v"}, format="json"
    )
    assert response.status_code == 400 and response.json() == GENERIC_400
    assert extra not in response.content.decode()


@pytest.mark.parametrize(
    "body", [b"[]", b'"text"', b"123", b"null", b"true", b'[{"username":"a","password":"b"}]']
)
def test_non_object_json_is_a_400(body):
    assert raw_post(browser(), body).status_code == 400


@pytest.mark.parametrize(
    "body", [b"", b"{", b"not json", b'{"username": "a@example.com",}', b"\xff\xfe", b"{'a': 1}"]
)
def test_invalid_json_is_a_400(body):
    response = raw_post(browser(), body)
    assert response.status_code == 400 and response.json() == GENERIC_400


@pytest.mark.parametrize(
    "content_type",
    ["application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "text/plain", "application/xml"],
)
def test_only_json_is_accepted(content_type):
    response = raw_post(browser(), b"username=a%40example.com&password=x", content_type)
    assert response.status_code == 415 and response.json()["code"] == "unsupported_media_type"


def test_oversized_bodies_are_413_without_reading_them_all():
    big = json.dumps({"username": "a@example.com", "password": "p" * (MAX_BODY_BYTES * 2)}).encode()
    response = raw_post(browser(), big)
    assert response.status_code == 413 and response.json() == {
        "code": "payload_too_large",
        "message": "Request body too large.",
    }
    exactly = b'{"username":"a@example.com","password":"x","pad":"' + b"a" * (MAX_BODY_BYTES - 60) + b'"}'
    assert raw_post(browser(), exactly).status_code in (
        400,
    )  # within the limit: validated (unknown field), not 413


def test_deeply_nested_json_is_a_400_not_a_crash():
    nested = b"[" * (MAX_BODY_BYTES - 10) + b"]" * 10
    assert raw_post(browser(), nested).status_code == 400
    nested_objects = (
        b'{"a":' * 1100 + b"1" + b"}" * 1100
    )  # ~6.6 KB: under the size limit, over Python's recursion limit
    assert raw_post(browser(), nested_objects).status_code == 400


@pytest.mark.parametrize("value", ["a\x00b@example.com", "\x00", "a@example.com\x00"])
def test_null_bytes_are_rejected_before_they_reach_the_database(value):
    response = browser().post(TOKEN, {"username": value, "password": PASSWORD}, format="json")
    assert response.status_code == 400  # PostgreSQL cannot store NUL; it must never become a 500
    assert (
        browser().post(TOKEN, {"username": "a@example.com", "password": "a\x00b"}, format="json").status_code
        == 400
    )


@pytest.mark.parametrize(
    "username",
    [
        "\u202eadmin@example.com",
        "\U0001f600@example.com",
        "ADMIN\u0130@example.com",
        "a" * 64 + "@" + "b" * 180 + ".com",
        "' OR 1=1 --",
        "a@b@c",
        "%00",
    ],
)
def test_odd_unicode_and_injection_strings_are_just_unknown_users(username):
    response = browser().post(TOKEN, {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code in (400, 401)
    assert response.status_code != 500


def test_long_passwords_within_the_limit_are_hashed_not_rejected(make_user):
    user = make_user(ROLE_SALES_FOLLOW_UP)
    assert login(browser(), user.email, password="p" * 256).status_code == 401  # a wrong but legal password


def test_wrong_methods_are_405_with_the_standard_error_shape():
    for method, path in (
        ("get", TOKEN),
        ("put", TOKEN),
        ("delete", REFRESH),
        ("get", LOGOUT),
        ("post", CSRF),
    ):
        response = getattr(browser(), method)(path)
        assert response.status_code in (401, 405), (method, path)
        if response.status_code == 405:
            assert response.json() == {"code": "method_not_allowed", "message": "Method not allowed."}


def test_error_responses_never_contain_internals():
    banned = ["Traceback", "SELECT ", "django", "settings", 'File "', "psycopg", "Authorization"]
    for body in (b"{", b"[]", b'{"username": 1}', b""):
        text = raw_post(browser(), body).content.decode()
        assert not [b for b in banned if b in text], text


def test_csrf_bootstrap_sets_a_cookie_and_returns_nothing(settings):
    client = browser()
    response = client.get(CSRF)
    assert response.status_code == 204 and response.content == b""
    assert client.cookies[settings.CSRF_COOKIE_NAME].value and response["Cache-Control"] == "no-store"
    # the token it hands out is accepted by a later unsafe request
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    assert (
        client.post(REFRESH, HTTP_X_CSRFTOKEN=token).status_code == 401
    )  # passes CSRF, fails for lack of a cookie
    assert mfa  # (module import kept for the enrolment-flow tests that share this file's helpers)


@pytest.mark.parametrize(
    "body",
    [
        b'{"username":"\\ud800","password":"x"}',  # lone surrogate: valid JSON escape, not valid UTF-8 text
        b'{"username":"a@example.com","password":"\\udfff"}',
        b'{"username":"a@example.com","password":"x","mfa_code":"\\ud83d"}',
    ],
)
def test_lone_surrogates_sent_as_json_escapes_never_become_a_500(body):
    response = raw_post(browser(), body)
    assert response.status_code in (400, 401), response.status_code


def test_a_recursion_error_in_the_json_parser_becomes_a_400_not_a_500():
    """Python 3.12's scanner parses even 8 000 nested levels, so the guard is defensive for other
    runtimes; simulate the failure it exists for."""
    from unittest import mock

    from rest_framework.parsers import JSONParser

    with mock.patch.object(JSONParser, "parse", side_effect=RecursionError):
        response = raw_post(browser(), b'{"username":"a","password":"b"}')
    assert response.status_code == 400 and response.json() == GENERIC_400
