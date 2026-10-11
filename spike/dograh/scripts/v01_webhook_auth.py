"""V01: analyse receiver captures for authentication and signing features."""
import re
import sys

from _common import load_captures

SIGNING_HINT = re.compile(r"sign|hmac|digest|timestamp|nonce|svix|webhook-id", re.I)
AUTH_HINT = re.compile(r"auth|api-key|token|secret|credential", re.I)


def analyze(captures: list) -> dict:
    names = sorted({h for c in captures for h in c["headers"]})
    return {"requests": len(captures), "header_names": names,
            "auth_like": [n for n in names if AUTH_HINT.search(n) or any(c["headers"].get(n, "").startswith("***") for c in captures)],
            "signing_like": [n for n in names if SIGNING_HINT.search(n)],
            "secret_shapes": {n: c["headers"][n] for c in captures[:1] for n in c["headers"]
                              if c["headers"][n].startswith("***")}}


if __name__ == "__main__":
    r = analyze(load_captures(sys.argv[1] if len(sys.argv) > 1 else "V01"))
    print(r)
    print("VERDICT:", "signing-like header present: inspect" if r["signing_like"]
          else "no signature/timestamp header observed" if r["requests"] else "no captures yet (PENDING_LIVE)")
