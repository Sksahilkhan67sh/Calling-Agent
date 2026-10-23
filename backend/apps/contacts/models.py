import uuid

from django.db import models

from apps.campaigns.models import Campaign
from apps.core.crypto import decrypt


class ContactQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(campaign__in=Campaign.objects.for_user(user))


class Contact(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending"
        DIALING = "Dialing"
        IN_CONVERSATION = "InConversation"
        DISCONNECTED = "Disconnected"
        RETRY_SCHEDULED = "RetryScheduled"
        RECONNECTING = "Reconnecting"
        COMPLETED = "Completed"
        COMPLETED_PARTIAL = "CompletedPartial"
        CLOSED = "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="contacts")
    phone_encrypted = models.BinaryField()
    phone_hmac = models.BinaryField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ContactQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["campaign", "status"])]
        constraints = [models.UniqueConstraint(fields=["phone_hmac", "campaign"], name="contact_unique_number_per_campaign")]

    @property
    def phone_number(self):
        return decrypt(self.phone_encrypted)
