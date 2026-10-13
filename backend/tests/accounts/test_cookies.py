"""Cookie flags, names and deletion (P2-08)."""

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts import cookies
from apps.accounts.tokens import TokenPair

PAIR = TokenPair(access="access-value", refresh="refresh-value")  # placeholders, not real tokens


def morsels(response: HttpResponse, settings):
    return response.cookies[settings.AUTH_ACCESS_COOKIE_NAME], response.cookies[
        settings.AUTH_REFRESH_COOKIE_NAME
    ]


def issued(settings) -> HttpResponse:
    response = HttpResponse()
    cookies.set_auth_cookies(response, PAIR)
    return response


def test_access_cookie_flags(settings):
    access, _ = morsels(issued(settings), settings)
    assert access.value == "access-value"
    assert access["httponly"] and access["secure"] and access["samesite"] == "Lax"
    assert access["path"] == "/" and access["max-age"] == settings.JWT_ACCESS_LIFETIME_SECONDS
    assert access["domain"] == ""  # no Domain attribute: host-only, as __Host- requires


def test_refresh_cookie_is_path_limited_to_the_auth_endpoints(settings):
    _, refresh = morsels(issued(settings), settings)
    assert refresh.value == "refresh-value"
    assert refresh["httponly"] and refresh["secure"] and refresh["samesite"] == "Lax"
    assert refresh["path"] == "/v1/auth/" and refresh["max-age"] == settings.JWT_REFRESH_LIFETIME_SECONDS


def test_prefixes_follow_the_cookie_rules(settings):
    access, refresh = morsels(issued(settings), settings)
    assert settings.AUTH_ACCESS_COOKIE_NAME.startswith("__Host-")  # Secure, Path=/, no Domain: all true above
    assert access["secure"] and access["path"] == "/" and access["domain"] == ""
    assert settings.AUTH_REFRESH_COOKIE_NAME.startswith("__Secure-")  # path-scoped, so __Host- is not allowed
    assert refresh["secure"] and refresh["path"] != "/"


def test_the_cookies_never_carry_the_tokens_in_a_readable_way(settings):
    response = issued(settings)
    assert not any(m["httponly"] is not True for m in response.cookies.values())


def test_cookie_domain_and_strict_samesite_are_honoured(settings):
    settings.AUTH_COOKIE_DOMAIN = "calls.test"
    settings.AUTH_COOKIE_SAMESITE = "Strict"
    access, refresh = morsels(issued(settings), settings)
    assert access["domain"] == refresh["domain"] == "calls.test"
    assert access["samesite"] == refresh["samesite"] == "Strict"


def test_cookies_are_not_secure_only_in_plain_http_development(settings):
    settings.AUTH_COOKIE_SECURE = False
    access, refresh = morsels(issued(settings), settings)
    assert not access["secure"] and not refresh["secure"] and access["httponly"] and refresh["httponly"]


@pytest.mark.parametrize("domain", [None, "calls.test"])
@pytest.mark.parametrize("samesite", ["Lax", "Strict"])
def test_deletion_mirrors_the_attributes_the_cookies_were_set_with(domain, samesite, settings):
    settings.AUTH_COOKIE_DOMAIN, settings.AUTH_COOKIE_SAMESITE = domain, samesite
    set_access, set_refresh = morsels(issued(settings), settings)
    response = HttpResponse()
    cookies.clear_auth_cookies(response)
    gone_access, gone_refresh = morsels(response, settings)
    for gone, original in ((gone_access, set_access), (gone_refresh, set_refresh)):
        assert gone.value == "" and gone["max-age"] == 0 and gone["expires"].startswith("Thu, 01 Jan 1970")
        assert gone["path"] == original["path"] and gone["domain"] == original["domain"]
        assert gone["samesite"] == original["samesite"] and gone["secure"] == original["secure"]


def test_deleting_the_refresh_cookie_targets_the_auth_path_only(settings):
    response = HttpResponse()
    cookies.clear_auth_cookies(response)
    _, refresh = morsels(response, settings)
    assert refresh["path"] == "/v1/auth/"  # a deletion on "/" would leave the real cookie in place


def test_no_store_headers():
    response = cookies.no_store(HttpResponse())
    assert response["Cache-Control"] == "no-store" and response["Pragma"] == "no-cache"


def test_rotating_the_csrf_token_requests_a_new_cookie_each_time():
    request = RequestFactory().get("/")
    cookies.rotate_csrf(request)
    first = request.META["CSRF_COOKIE"]
    assert request.META["CSRF_COOKIE_NEEDS_UPDATE"] is True
    cookies.rotate_csrf(request)
    assert request.META["CSRF_COOKIE"] != first
