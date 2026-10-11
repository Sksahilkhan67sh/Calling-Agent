import pytest

from apps.core import settings_utils as su


def test_required_returns_value_and_registers():
    assert su.required("X_A", env={"X_A": " v "}) == "v"
    assert "X_A" in su.READ_VARIABLES


@pytest.mark.parametrize("env", [{}, {"X_A": ""}, {"X_A": "   "}])
def test_required_missing_names_variable(env):
    with pytest.raises(su.ConfigError, match="X_A"):
        su.required("X_A", env=env)


def test_required_error_never_contains_value():
    with pytest.raises(su.ConfigError) as exc:
        su.as_int("X_SECRET", env={"X_SECRET": "hunter2-not-int"})
    assert "hunter2" not in str(exc.value) and "hunter2" not in repr(exc.value)


def test_optional_default_and_secret_flag():
    assert su.optional("X_B", "d", env={}) == "d"
    assert su.optional("X_B", env={"X_B": " z "}) == "z"
    su.optional("X_S", secret=True, env={})
    assert su.READ_VARIABLES["X_S"].secret is True


def test_as_int_paths():
    assert su.as_int("X_I", env={"X_I": "7"}) == 7
    assert su.as_int("X_I", 3, env={}) == 3
    with pytest.raises(su.ConfigError, match="required"):
        su.as_int("X_I", env={})
    with pytest.raises(su.ConfigError, match="integer"):
        su.as_int("X_I", env={"X_I": "x"})
    with pytest.raises(su.ConfigError, match="at least"):
        su.as_int("X_I", minimum=5, env={"X_I": "4"})
    with pytest.raises(su.ConfigError, match="at most"):
        su.as_int("X_I", maximum=5, env={"X_I": "6"})


def test_as_bool_paths():
    assert su.as_bool("X_B", env={"X_B": "Yes"}) is True
    assert su.as_bool("X_B", env={"X_B": "off"}) is False
    assert su.as_bool("X_B", True, env={}) is True
    with pytest.raises(su.ConfigError, match="required"):
        su.as_bool("X_B", env={})
    with pytest.raises(su.ConfigError, match="boolean"):
        su.as_bool("X_B", env={"X_B": "maybe"})


def test_as_list_paths():
    assert su.as_list("X_L", env={"X_L": " a, b ,,c"}) == ["a", "b", "c"]
    assert su.as_list("X_L", [], env={}) == []
    with pytest.raises(su.ConfigError, match="required"):
        su.as_list("X_L", env={})


def test_as_csv_hosts():
    assert su.as_csv_hosts("X_H", env={"X_H": "api.a.com,localhost"}) == ["api.a.com", "localhost"]
    with pytest.raises(su.ConfigError, match="wildcards"):
        su.as_csv_hosts("X_H", env={"X_H": "*.a.com"})
    with pytest.raises(su.ConfigError, match="invalid host"):
        su.as_csv_hosts("X_H", env={"X_H": "https://a.com"})
    with pytest.raises(su.ConfigError, match="at least one"):
        su.as_csv_hosts("X_H", [], env={})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("change-me-dev-only", True),
        ("django-insecure-abc", True),
        ("Placeholder1", True),
        ("k9fj2Hs8dLq0Zx", False),
    ],
)
def test_placeholder_detection(value, expected):
    assert su.looks_like_placeholder(value) is expected


def test_reject_placeholder_names_variable_only():
    with pytest.raises(su.ConfigError, match="MY_KEY") as exc:
        su.reject_placeholder("MY_KEY", "change-me-xyz")
    assert "change-me-xyz" not in str(exc.value)
    su.reject_placeholder("MY_KEY", "realvalue123")


def test_default_environment_is_os_environ(monkeypatch):
    monkeypatch.setenv("X_OS", "1")
    assert su.required("X_OS") == "1"
