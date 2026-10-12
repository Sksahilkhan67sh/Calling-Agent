"""Phase 2 authentication settings: posture, bounds and fail-fast rules (P2-02)."""

from datetime import timedelta

import pytest

from apps.core.settings_utils import ConfigError, as_origins
from tests.conftest import load_settings, make_prod_env

ORIGIN = "https://dashboard.calls.test"


def test_jwt_posture_is_fixed_in_code(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", prod_env, monkeypatch)
    jwt = s.SIMPLE_JWT
    assert jwt["ALGORITHM"] == "HS256" and jwt["ISSUER"] == "ai-calling-agent"
    assert jwt["AUDIENCE"] == "ai-calling-agent-dashboard"
    assert jwt["ROTATE_REFRESH_TOKENS"] is True and jwt["BLACKLIST_AFTER_ROTATION"] is True
    assert jwt["ACCESS_TOKEN_LIFETIME"] == timedelta(minutes=15)
    assert jwt["REFRESH_TOKEN_LIFETIME"] == timedelta(hours=24)
    assert jwt["SIGNING_KEY"] == prod_env["JWT_SIGNING_KEY"] != s.SECRET_KEY


def test_algorithm_cannot_be_changed_by_environment(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", {**prod_env, "JWT_ALGORITHM": "none"}, monkeypatch)
    assert s.SIMPLE_JWT["ALGORITHM"] == "HS256"


def test_lifetimes_are_configurable_within_bounds(prod_env, monkeypatch):
    env = {**prod_env, "JWT_ACCESS_LIFETIME_SECONDS": "600", "JWT_REFRESH_LIFETIME_SECONDS": "7200"}
    s = load_settings("config.settings.prod", env, monkeypatch)
    assert s.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] == timedelta(seconds=600)
    assert s.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] == timedelta(seconds=7200)


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"JWT_ACCESS_LIFETIME_SECONDS": "59"}, "at least"),
        ({"JWT_ACCESS_LIFETIME_SECONDS": "3601"}, "at most"),
        ({"JWT_REFRESH_LIFETIME_SECONDS": "60"}, "at least"),
        ({"JWT_REFRESH_LIFETIME_SECONDS": "2592001"}, "at most"),
        ({"AUTH_COOKIE_SAMESITE": "None"}, "Lax or Strict"),
        ({"AXES_FAILURE_LIMIT": "0"}, "at least"),
        ({"TRUSTED_PROXY_COUNT": "-1"}, "at least"),
        ({"TRUSTED_PROXY_COUNT": "11"}, "at most"),
        ({"TRUSTED_PROXY_COUNT": "one"}, "integer"),
        ({"LOGIN_RATE_LIMIT_PER_MINUTE": "0"}, "at least"),
        ({"MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS": "59"}, "at least"),
        ({"API_CLIENT_LAST_USED_WRITE_INTERVAL_SECONDS": "0"}, "at least"),
        ({"AUTH_TOKENS_IN_BODY": "maybe"}, "boolean"),
    ],
)
def test_prod_rejects_out_of_range_auth_values(override, needle, prod_env, monkeypatch):
    with pytest.raises(ConfigError, match=needle):
        load_settings("config.settings.prod", {**prod_env, **override}, monkeypatch)


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "https://*.calls.test",
        "http://dashboard.calls.test",
        "https://dashboard.calls.test/",
        ORIGIN + "/app",
    ],
)
@pytest.mark.parametrize("variable", ["CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS"])
def test_prod_refuses_wildcard_plaintext_or_path_origins(variable, origins, prod_env, monkeypatch):
    with pytest.raises(ConfigError) as exc:
        load_settings("config.settings.prod", {**prod_env, variable: origins}, monkeypatch)
    assert variable in str(exc.value) or "https://" in str(exc.value)


def test_credentialed_cors_requires_explicit_origins_in_prod(prod_env, monkeypatch):
    env = {k: v for k, v in prod_env.items() if k != "CORS_ALLOWED_ORIGINS"}
    with pytest.raises(ConfigError, match="CORS_ALLOWED_ORIGINS"):
        load_settings("config.settings.prod", env, monkeypatch)
    s = load_settings("config.settings.prod", prod_env, monkeypatch)
    assert s.CORS_ALLOW_CREDENTIALS is True and s.CORS_ALLOW_ALL_ORIGINS is False
    assert "*" not in s.CORS_ALLOWED_ORIGINS


@pytest.mark.parametrize(
    "roles", ["Admin", "Campaign Manager", "Sales / Follow-up", "Admin,Sales / Follow-up"]
)
def test_prod_requires_mfa_for_admin_and_campaign_manager(roles, prod_env, monkeypatch):
    with pytest.raises(ConfigError, match="must include Admin and Campaign Manager"):
        load_settings("config.settings.prod", {**prod_env, "MFA_REQUIRED_ROLES": roles}, monkeypatch)


def test_mfa_roles_reject_unknown_names_and_allow_extra_roles(prod_env, monkeypatch):
    with pytest.raises(ConfigError, match="unknown role"):
        load_settings(
            "config.settings.prod", {**prod_env, "MFA_REQUIRED_ROLES": "Admin,Campaign Manger"}, monkeypatch
        )
    roles = "Admin, Campaign Manager, Sales / Follow-up"
    s = load_settings("config.settings.prod", {**prod_env, "MFA_REQUIRED_ROLES": roles}, monkeypatch)
    assert s.MFA_REQUIRED_ROLES == ["Admin", "Campaign Manager", "Sales / Follow-up"]


def test_mfa_defaults_and_totp_parameters(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", prod_env, monkeypatch)
    assert s.MFA_REQUIRED_ROLES == ["Admin", "Campaign Manager"]
    assert (s.MFA_TOTP_ALGORITHM, s.MFA_TOTP_DIGITS, s.MFA_TOTP_PERIOD_SECONDS) == ("SHA1", 6, 30)
    assert s.MFA_TOTP_WINDOW_STEPS == 1 and s.MFA_ENROLLMENT_TOKEN_LIFETIME_SECONDS == 600


def test_cookie_posture_in_production(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", prod_env, monkeypatch)
    assert s.AUTH_COOKIE_SECURE is True and s.AUTH_COOKIE_SAMESITE == "Lax" and s.AUTH_COOKIE_DOMAIN is None
    assert s.AUTH_TOKENS_IN_BODY is False
    assert s.AUTH_ACCESS_COOKIE_NAME == "__Host-access" and s.CSRF_COOKIE_NAME == "__Host-csrftoken"
    assert s.AUTH_REFRESH_COOKIE_NAME == "__Secure-refresh"  # path-scoped, so __Host- is not allowed
    assert s.AUTH_REFRESH_COOKIE_PATH == "/v1/auth/"
    assert s.CSRF_COOKIE_SECURE is True and s.CSRF_COOKIE_HTTPONLY is False
    assert s.CSRF_COOKIE_SAMESITE == "Lax" and s.CSRF_TRUSTED_ORIGINS == [ORIGIN]


def test_cookie_domain_switches_to_secure_prefix_and_strict_is_honoured(prod_env, monkeypatch):
    env = {**prod_env, "AUTH_COOKIE_DOMAIN": "calls.test", "AUTH_COOKIE_SAMESITE": "strict"}
    s = load_settings("config.settings.prod", env, monkeypatch)
    assert s.AUTH_ACCESS_COOKIE_NAME == "__Secure-access" and s.CSRF_COOKIE_NAME == "__Secure-csrftoken"
    assert s.AUTH_COOKIE_SAMESITE == "Strict" == s.CSRF_COOKIE_SAMESITE
    assert s.CSRF_COOKIE_DOMAIN == "calls.test"


def test_dev_uses_plain_cookie_names_over_http(monkeypatch):
    s = load_settings("config.settings.dev", make_prod_env(), monkeypatch)
    assert s.AUTH_COOKIE_SECURE is False
    assert (s.AUTH_ACCESS_COOKIE_NAME, s.AUTH_REFRESH_COOKIE_NAME, s.CSRF_COOKIE_NAME) == (
        "access",
        "refresh",
        "csrftoken",
    )


def test_non_prod_defaults_do_not_need_the_new_variables(monkeypatch):
    s = load_settings("config.settings.test", {}, monkeypatch)
    assert s.AXES_FAILURE_LIMIT == 5 and s.TRUSTED_PROXY_COUNT == 0
    assert s.AXES_LOCKOUT_PARAMETERS == [["username", "ip_address"]]
    assert s.API_CLIENT_LAST_USED_WRITE_INTERVAL_SECONDS == 60


def test_login_throttle_rate_comes_from_environment_in_prod(prod_env, monkeypatch):
    s = load_settings("config.settings.prod", {**prod_env, "LOGIN_RATE_LIMIT_PER_MINUTE": "7"}, monkeypatch)
    assert s.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login"] == "7/min"


@pytest.mark.parametrize(
    "value", ["https://a.test", "http://localhost:3000", "https://a.test:8443,https://b.test"]
)
def test_as_origins_accepts_plain_origins(value):
    assert as_origins("X", env={"X": value}) == value.split(",")


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "a.test",
        "https://a.test/",
        "https://a.test/x",
        "ftp://a.test",
        "https://a.test?x=1",
        "https://-bad",
    ],
)
def test_as_origins_rejects_everything_else(value):
    with pytest.raises(ConfigError) as exc:
        as_origins("X", env={"X": value})
    assert value not in str(exc.value)
