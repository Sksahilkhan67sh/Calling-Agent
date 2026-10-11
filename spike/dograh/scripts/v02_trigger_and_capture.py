"""V02/V01/V03 driver: start ONE guarded test call carrying our correlation ids in initial_context.

Run the receiver first (webhook_receiver.py --item V02). Usage: v02_trigger_and_capture.py +E164NUMBER
"""
import os
import sys
import uuid

from _common import require_live, save_evidence, utcnow
from dograh_client import DograhClient

if __name__ == "__main__":
    require_live("V02", ["Create a webhook credential (API_KEY, header X-Dograh-Webhook-Secret) in the Dograh UI",
                         "Point the workflow's webhook node at PUBLIC_WEBHOOK_URL with the template from Dograh-Integration 4.2",
                         "Start webhook_receiver.py --item V02, then run this script with an owned test number",
                         "Compare captured payload with the template; save a never-connected sample too (leave a call unanswered)"])
    number = sys.argv[1]
    ctx = {"attempt_id": str(uuid.uuid4()), "campaign_id": "spike-campaign", "contact_ref": "spike-contact-1",
           "test_notice": "This is a test call"}
    r = DograhClient.from_env().start_call(os.environ["DOGRAH_WORKFLOW_UUID"], number, ctx, "V02 payload rendering")
    print(r.status, r.error, r.body)
    save_evidence("V02", "trigger_response.json", {"at": utcnow(), "status": r.status, "body": r.body,
                                                   "initial_context_sent": ctx})
