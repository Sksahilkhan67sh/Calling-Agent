import hmac
import logging

from django.conf import settings
from rest_framework import authentication, exceptions

log = logging.getLogger(__name__)


class WebhookPrincipal:
    is_authenticated = True
    pk = "dograh"  # throttle cache key


class DograhWebhookAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        supplied = request.META.get("HTTP_" + settings.DOGRAH_WEBHOOK_HEADER_NAME.upper().replace("-", "_"), "").encode()
        # current secret and, during rotation only, the previous one; compare every candidate to stay constant-time
        ok = [hmac.compare_digest(supplied, s.encode()) for s in (settings.DOGRAH_WEBHOOK_SECRET, settings.DOGRAH_WEBHOOK_SECRET_PREVIOUS) if s]
        if not any(ok):
            log.error("webhook authentication failed")
            raise exceptions.AuthenticationFailed("invalid webhook credential")
        return WebhookPrincipal(), None

    def authenticate_header(self, request):
        return settings.DOGRAH_WEBHOOK_HEADER_NAME
