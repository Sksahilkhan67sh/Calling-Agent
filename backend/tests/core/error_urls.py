"""Throwaway URL conf that raises every exception class the API must render as the contract's Error."""

from collections.abc import Callable

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import SuspiciousOperation
from django.http import Http404, HttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_protect
from rest_framework import exceptions as e
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import CookieJWTAuthentication
from config.urls import handler400, handler403, handler404, handler500  # noqa: F401  (the real handlers)

SECRET_TEXT = "SELECT password FROM users WHERE token='hunter2'"  # must never reach a response


class Teapot(e.APIException):
    status_code = 418


class Raise(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []
    make_exc: Callable[[], Exception] = lambda: RuntimeError(SECRET_TEXT)  # noqa: E731

    def get(self, request):
        raise self.make_exc()  # a fresh instance per request: DRF mutates status_code on the exception

    def post(self, request):
        return Response({"ok": bool(request.data is not None)})  # reading the body triggers parsing


EXCEPTIONS: dict[str, Callable[[], Exception]] = {
    "validation": lambda: e.ValidationError({"password": [SECRET_TEXT]}),
    "parse": lambda: e.ParseError(SECRET_TEXT),
    "authentication-failed": lambda: e.AuthenticationFailed(SECRET_TEXT),
    "not-authenticated": lambda: e.NotAuthenticated(SECRET_TEXT),
    "permission-denied": lambda: e.PermissionDenied(SECRET_TEXT),
    "django-permission-denied": lambda: DjangoPermissionDenied(SECRET_TEXT),
    "django-404": lambda: Http404(SECRET_TEXT),
    "not-found": lambda: e.NotFound(SECRET_TEXT),
    "method-not-allowed": lambda: e.MethodNotAllowed("PUT", detail=SECRET_TEXT),
    "not-acceptable": lambda: e.NotAcceptable(SECRET_TEXT),
    "unsupported-media-type": lambda: e.UnsupportedMediaType("text/plain", detail=SECRET_TEXT),
    "throttled": lambda: e.Throttled(wait=30, detail=SECRET_TEXT),
    "unknown-api-exception": lambda: Teapot(SECRET_TEXT),
    "unhandled": lambda: RuntimeError(SECRET_TEXT),
}


def plain_not_found(request):
    raise Http404(SECRET_TEXT)


def plain_forbidden(request):
    raise DjangoPermissionDenied(SECRET_TEXT)


def plain_suspicious(request):
    raise SuspiciousOperation(SECRET_TEXT)


def plain_crash(request):
    raise RuntimeError(SECRET_TEXT)


@csrf_protect
def plain_csrf_form(request):
    return HttpResponse("ok")


urlpatterns = [
    *[path(f"raise/{name}/", Raise.as_view(make_exc=factory)) for name, factory in EXCEPTIONS.items()],
    # The same two exceptions on a view with a real authenticator, which is what makes DRF answer 401.
    *[
        path(
            f"challenge/{name}/",
            Raise.as_view(make_exc=EXCEPTIONS[name], authentication_classes=[CookieJWTAuthentication]),
        )
        for name in ("authentication-failed", "not-authenticated")
    ],
    path("plain/404/", plain_not_found),
    path("plain/403/", plain_forbidden),
    path("plain/400/", plain_suspicious),
    path("plain/500/", plain_crash),
    path("plain/csrf/", plain_csrf_form),
]
