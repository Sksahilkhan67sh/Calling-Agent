import pytest
from django.test import override_settings

from apps.core import health


def test_liveness_fixed_and_anonymous(client):
    response = client.get("/healthz")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


@override_settings(APP_VERSION="abc1234")
def test_version_included_when_valid(client):
    assert client.get("/healthz").json()["version"] == "abc1234"


@override_settings(APP_VERSION="bad version; <script>")
def test_version_omitted_when_invalid(client):
    assert "version" not in client.get("/healthz").json()


def _patch(monkeypatch, **overrides):
    ok = lambda: None  # noqa: E731

    def fail():
        raise RuntimeError("postgres://u:SECRETPW@db:5432/x unreachable")

    checks = {"database": ok, "redis": ok, "broker": ok}
    checks.update(dict.fromkeys(overrides, fail))
    monkeypatch.setattr(health, "CHECKS", checks)


def test_ready_all_healthy(client, monkeypatch):
    _patch(monkeypatch)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "redis": True, "broker": True}


@pytest.mark.parametrize("failing", ["database", "redis", "broker"])
def test_ready_names_failure_without_details(client, monkeypatch, failing):
    _patch(monkeypatch, **{failing: True})
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"][failing] is False and body["status"] == "unavailable"
    assert "SECRETPW" not in response.content.decode() and "postgres://" not in response.content.decode()


def test_hung_dependency_cannot_hang_probe(client, monkeypatch):
    import time

    hang = lambda: time.sleep(3)  # noqa: E731
    monkeypatch.setattr(health, "CHECKS", {"database": hang, "redis": lambda: None, "broker": lambda: None})
    monkeypatch.setattr(health, "CHECK_TIMEOUT_SECONDS", 0.2)
    start = time.perf_counter()
    response = client.get("/readyz")
    assert response.status_code == 503 and response.json()["checks"]["database"] is False
    assert time.perf_counter() - start < 1.5


def test_health_not_throttled_by_user_scopes(client):
    assert health.HealthLive.throttle_classes == [] and health.HealthReady.throttle_classes == []


@pytest.mark.integration
@pytest.mark.django_db
def test_ready_real_services_healthy(client):
    response = client.get("/readyz")
    assert response.status_code == 200, response.content
    assert response.json()["checks"] == {"database": True, "redis": True, "broker": True}


@pytest.mark.integration
def test_ready_real_services_unreachable(client, monkeypatch):
    from django.conf import settings

    broken_db = {**settings.DATABASES["default"], "PORT": "1"}
    with override_settings(
        DATABASES={"default": broken_db},
        CACHE_REDIS_URL="redis://127.0.0.1:1/0",
        CELERY_BROKER_URL="redis://127.0.0.1:1/0",
    ):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False, "redis": False, "broker": False}
