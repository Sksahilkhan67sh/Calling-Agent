"""Throwaway webhook receiver. Saves redacted captures to docs/phase-0/evidence/<item>/.

Modes: ok (200), fail500 (always 500), fail_then_ok (500 for the first N deliveries, then 200),
slow (sleep before 200). Never stores raw/unredacted data and never prints secrets.
"""
import argparse
import datetime
import json
import pathlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from redact import redact_body, redact_headers, redact_url

EVIDENCE = pathlib.Path(__file__).resolve().parents[2] / "docs/phase-0/evidence"


def make_server(item: str, mode: str = "ok", port: int = 0, fail_count: int = 1,
                slow_s: float = 35.0, out_dir: pathlib.Path | None = None):
    out = (out_dir or EVIDENCE) / item
    out.mkdir(parents=True, exist_ok=True)
    state = {"n": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("content-length", 0)))
            with lock:
                state["n"] += 1
                n = state["n"]
            now = datetime.datetime.now(datetime.UTC)
            record = {"seq": n, "received_at": now.isoformat(), "method": self.command,
                      "path": redact_url("http://x" + self.path),
                      "headers": redact_headers(dict(self.headers.items())),
                      "body": redact_body(raw)}
            (out / f"{n:03d}_{now.strftime('%H%M%S')}.json").write_text(json.dumps(record, indent=2))
            if mode == "slow":
                time.sleep(slow_s)
            fail = mode == "fail500" or (mode == "fail_then_ok" and n <= fail_count)
            self.send_response(500 if fail else 200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"error"}' if fail else b'{"status":"ok"}')

        def log_message(self, *args):  # request lines can carry tokens; stay silent
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True, help="evidence folder, e.g. V01")
    ap.add_argument("--mode", default="ok", choices=["ok", "fail500", "fail_then_ok", "slow"])
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--fail-count", type=int, default=1)
    ap.add_argument("--slow-seconds", type=float, default=35.0)
    a = ap.parse_args()
    srv = make_server(a.item, a.mode, a.port, a.fail_count, a.slow_seconds)
    print(f"receiver on 127.0.0.1:{srv.server_address[1]} item={a.item} mode={a.mode}")
    srv.serve_forever()
