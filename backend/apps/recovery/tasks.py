import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.calls.models import RecordingRef, Transcript

from .models import WorkingMemorySnapshot
from .services import RETRYABLE, s3

log = logging.getLogger(__name__)


@shared_task(queue="recovery")
def sweep_retention():
    """Delete expired recordings, transcripts and working memory. Never touches suppression."""
    cutoff = timezone.now() - timedelta(days=settings.RETENTION_DAYS)
    for ref in RecordingRef.objects.filter(attempt__ended_at__lt=cutoff):
        try:
            s3().delete_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=ref.storage_path)
        except RETRYABLE:  # keep the row so the next sweep retries the object delete
            log.exception("recording delete failed", extra={"attempt_id": str(ref.attempt_id)})
            continue
        ref.delete()
    Transcript.objects.filter(attempt__ended_at__lt=cutoff).delete()
    WorkingMemorySnapshot.objects.filter(snapshotted_at__lt=cutoff).delete()
