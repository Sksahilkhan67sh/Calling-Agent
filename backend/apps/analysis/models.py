import uuid

from django.db import models

from apps.calls.models import CallAttempt, RecordingRef, Transcript
from apps.contacts.models import Contact


class Analysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.OneToOneField(CallAttempt, on_delete=models.CASCADE, related_name="analysis")
    interest_classification = models.CharField(max_length=16)
    lead_score = models.PositiveSmallIntegerField()
    qualification_level = models.CharField(max_length=20)
    temperature_tag = models.CharField(max_length=4)
    conversion_probability = models.PositiveSmallIntegerField()
    score_confidence = models.CharField(max_length=8)
    feedback = models.JSONField()
    disposition = models.CharField(max_length=128, blank=True)
    scoring_version = models.CharField(max_length=8)
    analyzed_at = models.DateTimeField(auto_now_add=True)


class FinalOutput(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.OneToOneField(Contact, on_delete=models.CASCADE, related_name="final_output")  # one per terminal call
    source_attempt = models.ForeignKey(CallAttempt, on_delete=models.PROTECT, related_name="+")
    transcript_ref = models.ForeignKey(Transcript, null=True, on_delete=models.SET_NULL, related_name="+")
    recording_ref = models.ForeignKey(RecordingRef, null=True, on_delete=models.SET_NULL, related_name="+")
    feedback = models.JSONField()
    interest_detection = models.JSONField()
    lead_score_summary = models.JSONField()
    call_summary = models.JSONField()
    generated_at = models.DateTimeField(auto_now_add=True)
