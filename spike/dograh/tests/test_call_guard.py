import pytest
import call_guard


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LIVE_TESTING", "yes")
    monkeypatch.setenv("SPIKE_TEST_NUMBERS", "+919876543210")
    monkeypatch.setenv("MAX_TEST_CALLS", "1")
    return tmp_path / "ledger.md"


def test_refused_when_live_testing_off(env, monkeypatch):
    monkeypatch.setenv("LIVE_TESTING", "no")
    with pytest.raises(call_guard.CallRefused):
        call_guard.authorize("+919876543210", "t", env)


def test_refused_for_unowned_number(env):
    with pytest.raises(call_guard.CallRefused, match="SPIKE_TEST_NUMBERS"):
        call_guard.authorize("+919876500000", "t", env)


def test_zero_cap_refuses_everything(env, monkeypatch):
    monkeypatch.setenv("MAX_TEST_CALLS", "0")
    with pytest.raises(call_guard.CallRefused, match="cap"):
        call_guard.authorize("+919876543210", "t", env)


def test_allows_once_then_cap_and_ledger_is_masked(env):
    call_guard.authorize("+919876543210", "answer test", env)
    text = env.read_text()
    assert "+91********10" in text and "+919876543210" not in text
    with pytest.raises(call_guard.CallRefused, match="cap"):
        call_guard.authorize("+919876543210", "again", env)
