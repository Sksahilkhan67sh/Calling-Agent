"""V13: procedure only. Rotation endpoints are under /user/api-keys and their auth scheme is not documented."""
from _common import require_live

require_live("V13", [
    "Create key B on a throwaway organization (UI or POST /user/api-keys); note it is shown once",
    "Confirm key B works (get-run), then archive key A (DELETE /user/api-keys/{id}); confirm key A now returns 401",
    "Reactivate key A (PUT .../reactivate) and confirm it works again; check last_used_at on both",
    "Confirm whether these key-management calls need a user JWT rather than an API key",
    "Check whether the reverse proxy can allowlist source IPs for /api/v1/public/* and /api/v1/workflow/*",
    "Check what the access log records for key usage (key id vs nothing)"])
