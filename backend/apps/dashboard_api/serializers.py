from rest_framework import serializers

from apps.analysis.models import FinalOutput
from apps.calls.models import CallAttempt, DisconnectEvent, Transcript


class CallAttemptSerializer(serializers.ModelSerializer):
    contact_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CallAttempt
        fields = ["id", "contact_id", "attempt_number", "state", "connection_failure_reason", "disconnect_reason",
                  "recording_consent", "started_at", "ended_at"]


class DisconnectEventSerializer(serializers.ModelSerializer):
    attempt_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = DisconnectEvent
        fields = ["id", "attempt_id", "reason", "occurred_at", "retry_approved"]


class TranscriptSerializer(serializers.ModelSerializer):
    attempt_id = serializers.UUIDField(read_only=True)
    content = serializers.CharField(read_only=True)

    class Meta:
        model = Transcript
        fields = ["attempt_id", "is_partial", "content", "updated_at"]


class FinalOutputSerializer(serializers.ModelSerializer):
    contact_id = serializers.UUIDField(read_only=True)
    # Raw transcript text and recording URLs are served only by the audited, role-restricted endpoints
    transcript = serializers.SerializerMethodField()
    recording = serializers.SerializerMethodField()

    class Meta:
        model = FinalOutput
        fields = ["id", "contact_id", "source_attempt_id", "transcript", "recording", "feedback", "interest_detection",
                  "lead_score_summary", "call_summary", "generated_at"]

    def get_transcript(self, o):
        t = o.transcript_ref
        return t and {"attempt_id": str(t.attempt_id), "is_partial": t.is_partial, "updated_at": t.updated_at}

    def get_recording(self, o):
        r = o.recording_ref
        return r and {"attempt_id": str(r.attempt_id), "duration_seconds": r.duration_seconds}
