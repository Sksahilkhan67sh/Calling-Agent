"""V07: procedure only (nothing safe to automate). Use v06_status_matrix.py on the captures afterwards."""
from _common import require_live

require_live("V07", [
    "Call 1: answer, talk 20 s, hang up abruptly from the phone. Capture webhook + get-run (V04 script).",
    "Call 2: answer, switch the phone to airplane mode mid-sentence. Capture the same.",
    "Call 3: let the agent end the call normally (end-call node). Capture the same.",
    "Record call_status, call_disposition, duration, is_completed and whether the webhook fired at all for each.",
    "Check whether the webhook node fires when the run ends abnormally (docs: 'when reached'); if not, reconciler is primary.",
    "Decision: stay with run-ended notification (default) unless sub-second visibility is a requirement."])
