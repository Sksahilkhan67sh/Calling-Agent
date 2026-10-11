"""V03: from receiver captures (fail500 / fail_then_ok modes) compute delivery attempts per run."""
import datetime
import sys

from _common import body_json, load_captures


def matrix(captures: list) -> dict:
    runs: dict = {}
    for c in captures:
        runs.setdefault(str(body_json(c).get("run_id", "?")), []).append(c)
    out = {}
    for run, cs in runs.items():
        times = [datetime.datetime.fromisoformat(c["received_at"]) for c in cs]
        stable = lambda c: {k: v for k, v in c["headers"].items() if k.lower() not in ("date", "content-length")}
        out[run] = {"attempts": len(cs),
                    "intervals_s": [round((b - a).total_seconds(), 1) for a, b in zip(times, times[1:])],
                    "headers_identical": all(stable(c) == stable(cs[0]) for c in cs),
                    "body_identical": all(c["body"] == cs[0]["body"] for c in cs)}
    return out


if __name__ == "__main__":
    for run, row in matrix(load_captures(sys.argv[1] if len(sys.argv) > 1 else "V03")).items():
        print(run, row)
