import re

from pythonjsonlogger.json import JsonFormatter

_RULES = [
    (
        re.compile(
            r"""(?ix)((?:authorization|cookie|x-api-key|api[_-]?key|secret|password|token|signature)
            ["']?\s*[:=]\s*["']?)(?:(?:bearer|basic)\s+)?[^\s,;&"'}]+"""
        ),
        r"\1[redacted]",
    ),
    (re.compile(r"(?i)([?&](?:token|key|sig|signature|x-amz-[\w-]+)=)[^&\s\"']+"), r"\1[redacted]"),
    (re.compile(r"(?i)https?://[^\s\"'<>]*(?:recording|x-amz-)[^\s\"'<>]*"), "[recording-url]"),
    (re.compile(r"\+\d[\d ()-]{7,}\d|\b\d{10,15}\b"), "[phone]"),
]


def redact(text):
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text


class RedactingJsonFormatter(JsonFormatter):
    # Redacting the rendered line covers messages, extras and tracebacks in one place
    def format(self, record):
        return redact(super().format(record))
