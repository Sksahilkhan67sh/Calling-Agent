import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core import throttles


def _view(throttle_class):
    class V(APIView):
        authentication_classes: list = []
        permission_classes = [AllowAny]
        throttle_classes = [throttle_class]

        def get(self, request):
            return Response({"ok": True})

    return V.as_view()


def _rates(**rates):
    from django.conf import settings

    return {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **rates},
    }


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def _hit(view, ip="10.0.0.1"):
    return view(APIRequestFactory().get("/", REMOTE_ADDR=ip))


def test_rates_come_from_settings():
    from django.conf import settings

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert set(rates) == {"login", "api-user", "api-client", "webhook"}
    assert rates["login"] == "5/min"


@pytest.mark.parametrize(
    "klass",
    [
        throttles.LoginThrottle,
        throttles.ApiUserThrottle,
        throttles.ApiClientThrottle,
        throttles.WebhookThrottle,
    ],
)
def test_exceeded_returns_429_with_retry_after(klass):
    from rest_framework.throttling import SimpleRateThrottle

    with override_settings(REST_FRAMEWORK=_rates(**{klass.scope: "2/min"})):
        SimpleRateThrottle.THROTTLE_RATES = _rates(**{klass.scope: "2/min"})["DEFAULT_THROTTLE_RATES"]
        view = _view(klass)
        assert [_hit(view).status_code for _ in range(3)] == [200, 200, 429]
        blocked = _hit(view)
        assert blocked.status_code == 429 and int(blocked["Retry-After"]) > 0
        assert _hit(view, ip="10.0.0.2").status_code == 200  # other client unaffected


def test_scopes_are_isolated():
    from rest_framework.throttling import SimpleRateThrottle

    SimpleRateThrottle.THROTTLE_RATES = _rates(login="1/min", webhook="5/min")["DEFAULT_THROTTLE_RATES"]
    login, hook = _view(throttles.LoginThrottle), _view(throttles.WebhookThrottle)
    assert _hit(login).status_code == 200 and _hit(login).status_code == 429
    assert _hit(hook).status_code == 200


def test_identity_resolution():
    class R:
        META = {"REMOTE_ADDR": "9.9.9.9"}
        headers: dict = {}

        class user:  # noqa: N801
            is_authenticated = True
            pk = "u-1"

        class auth:  # noqa: N801
            client_id = "c-1"

    from rest_framework.throttling import SimpleRateThrottle

    SimpleRateThrottle.THROTTLE_RATES = _rates()["DEFAULT_THROTTLE_RATES"]
    assert throttles.ApiUserThrottle()._identity(R()) == "user:u-1"
    assert throttles.ApiClientThrottle()._identity(R()) == "client:c-1"
    R.user.is_authenticated = False
    R.auth = None
    assert throttles.ApiUserThrottle()._identity(R()) == "9.9.9.9"
    assert throttles.ApiClientThrottle()._identity(R()) == "9.9.9.9"


@pytest.mark.integration
def test_throttle_counts_in_real_redis(redis_client):
    from django.conf import settings
    from rest_framework.throttling import SimpleRateThrottle

    client, prefix = redis_client
    SimpleRateThrottle.THROTTLE_RATES = _rates(webhook="2/min")["DEFAULT_THROTTLE_RATES"]
    caches = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": settings.CACHE_REDIS_URL,
            "KEY_PREFIX": prefix.rstrip(":"),
        }
    }
    with override_settings(CACHES=caches):
        view = _view(throttles.WebhookThrottle)
        assert [_hit(view).status_code for _ in range(3)] == [200, 200, 429]
        assert any(k.startswith(prefix.rstrip(":")) or prefix.rstrip(":") in k for k in client.keys("*"))
