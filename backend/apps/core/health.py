"""Liveness and readiness probes. The only anonymous surface in Phase 1."""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

import redis
from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from kombu import Connection
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import PublicEndpoint

CHECK_TIMEOUT_SECONDS = 2.0
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def check_database() -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    finally:
        connection.close()


def check_redis() -> None:
    client = redis.Redis.from_url(settings.CACHE_REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    try:
        client.ping()
    finally:
        client.close()


def check_broker() -> None:
    with Connection(settings.CELERY_BROKER_URL, connect_timeout=1) as conn:
        conn.ensure_connection(max_retries=1, interval_start=0, timeout=2)


CHECKS: dict[str, Callable[[], None]] = {
    "database": check_database,
    "redis": check_redis,
    "broker": check_broker,
}


def _version() -> dict[str, str]:
    version = getattr(settings, "APP_VERSION", "")
    return {"version": version} if _VERSION_PATTERN.match(version or "") else {}


@extend_schema(exclude=True)  # internal probes are not part of the API contract
class _ProbeView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [PublicEndpoint]
    throttle_classes: list[Any] = []
    renderer_classes = [JSONRenderer]


@extend_schema(exclude=True)
class HealthLive(_ProbeView):
    def get(self, request: Request) -> Response:
        return Response({"status": "ok", **_version()})


@extend_schema(exclude=True)
class HealthReady(_ProbeView):
    def get(self, request: Request) -> Response:
        # Dependency details are never returned: only the check names and a boolean.
        results: dict[str, bool] = {}
        executor = ThreadPoolExecutor(max_workers=len(CHECKS))
        futures = {name: executor.submit(fn) for name, fn in CHECKS.items()}
        for name, future in futures.items():
            try:
                future.result(timeout=CHECK_TIMEOUT_SECONDS)
                results[name] = True
            except (FutureTimeout, Exception):  # noqa: BLE001 - any failure means "not ready"
                results[name] = False
        executor.shutdown(wait=False, cancel_futures=True)
        healthy = all(results.values())
        body = {"status": "ok" if healthy else "unavailable", "checks": results, **_version()}
        return Response(body, status=200 if healthy else 503)
