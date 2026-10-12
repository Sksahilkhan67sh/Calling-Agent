"""Gunicorn settings for the API container (ASGI via the Uvicorn worker class)."""

import os

from apps.core.logging import build_logging_config

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")  # noqa: S104 - container network interface
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "uvicorn_worker.UvicornWorker"
timeout = 30
graceful_timeout = 30
keepalive = 5

# The access log never includes the query string (%(U)s is the path only), so URL tokens
# cannot reach the logs. Every handler also runs the redaction filter.
accesslog = "-"
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(b)s %(L)s'
logconfig_dict = build_logging_config(level=os.environ.get("LOG_LEVEL", "INFO"))
