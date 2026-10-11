"""Test-only settings: same as test settings but the heartbeat fires every 2 seconds."""

from config.settings.test import *  # noqa: F403

CELERY_BEAT_SCHEDULE = {"core-heartbeat": {"task": "apps.core.tasks.heartbeat", "schedule": 2.0}}
