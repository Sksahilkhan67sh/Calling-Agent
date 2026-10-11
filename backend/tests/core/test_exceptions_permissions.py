import pytest
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core.exceptions import safe_exception_handler


class _Boom(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []

    def get(self, request):
        raise RuntimeError("SELECT * FROM secrets WHERE password='hunter2'")


def test_unhandled_error_returns_generic_500_without_internals(caplog):
    response = _Boom.as_view()(APIRequestFactory().get("/"))
    assert response.status_code == 500
    assert response.data == {"detail": "Internal server error."}
    assert "hunter2" not in str(response.data)


def test_drf_errors_keep_their_response():
    response = safe_exception_handler(NotFound(), {"view": None, "request": None})
    assert response is not None and response.status_code == 404


@pytest.mark.parametrize("debug", [True, False])
def test_default_deny_message_only_in_debug(debug, settings):
    settings.DEBUG = debug

    class Undeclared(APIView):
        throttle_classes: list = []

    response = Undeclared.as_view()(APIRequestFactory().get("/"))
    assert response.status_code == 403
    assert ("declares no permission_classes" in str(response.data["detail"])) is debug
