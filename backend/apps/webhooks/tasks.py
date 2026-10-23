import logging

from celery import shared_task

from apps.calls.services import apply_run
from apps.voice_runtime.client import DograhClient, DograhError

from .models import WebhookReceipt

log = logging.getLogger(__name__)


@shared_task(queue="webhook", autoretry_for=(DograhError,), retry_backoff=True, max_retries=5)
def process_run_result(receipt_id):
    """Trust boundary: the body only announced the run; the pulled run decides (Webhook Spec §4A.3)."""
    receipt = WebhookReceipt.objects.get(pk=receipt_id)
    if receipt.status != WebhookReceipt.Status.RECEIVED:
        return
    result = apply_run(receipt.claimed_attempt_id, DograhClient().get_run(receipt.run_id))
    if result == "pending":  # not terminal yet; the reconciler picks it up past its ceiling
        return
    receipt.status = WebhookReceipt.Status.PROCESSED if result == "applied" else WebhookReceipt.Status.REJECTED
    receipt.save(update_fields=["status"])
