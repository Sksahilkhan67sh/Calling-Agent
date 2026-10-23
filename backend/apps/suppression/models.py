from django.db import models

from apps.contacts.models import Contact


class Suppression(models.Model):
    class Source(models.TextChoices):
        AGENT_IN_CALL = "agent_in_call"
        MANUAL_API = "manual_api"

    # PROTECT: suppression must outlive normal retention, so a suppressed contact cannot be deleted
    contact = models.OneToOneField(Contact, primary_key=True, on_delete=models.PROTECT, related_name="suppression")
    phone_hmac = models.BinaryField(db_index=True)
    reason = models.TextField(blank=True)
    source = models.CharField(max_length=16, choices=Source.choices)
    requested_at = models.DateTimeField(auto_now_add=True)
