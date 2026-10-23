import hashlib

from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import DograhWebhookAuthentication
from .models import WebhookReceipt
from .tasks import process_run_result


class RunResultSerializer(serializers.Serializer):
    attempt_id = serializers.UUIDField()
    run_id = serializers.CharField(max_length=64)  # extra fields ignored; body URLs are never fetched


class DograhRunWebhook(APIView):
    authentication_classes = [DograhWebhookAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def post(self, request):
        digest = hashlib.sha256(request.body).digest()  # read before request.data consumes the stream
        data = RunResultSerializer(data=request.data)
        if not data.is_valid():
            return Response(data.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        receipt, _ = WebhookReceipt.objects.get_or_create(
            provider="dograh", run_id=data.validated_data["run_id"], event_type="run_completed",
            defaults={"claimed_attempt_id": data.validated_data["attempt_id"], "payload_hash": digest})
        if receipt.status == WebhookReceipt.Status.RECEIVED:  # a redelivery re-enqueues; the task is idempotent
            process_run_result.delay(str(receipt.pk))
        return Response(status=status.HTTP_200_OK)
