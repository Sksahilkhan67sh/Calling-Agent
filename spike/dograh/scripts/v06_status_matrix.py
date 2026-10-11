"""V06/V07: tabulate observed (call_status, call_disposition, duration) from webhook captures or run snapshots."""
import sys
from collections import Counter

from _common import body_json, load_captures


def rows(captures: list) -> list:
    out = []
    for c in captures:
        b = body_json(c)
        out.append((b.get("call_status"), b.get("call_disposition"), b.get("mapped_call_disposition"),
                    b.get("duration_seconds"), b.get("recording_url") not in (None, "", "None")))
    return out


def table(captures: list) -> Counter:
    return Counter((s, d, m, rec) for s, d, m, _dur, rec in rows(captures))


if __name__ == "__main__":
    for key, n in table(load_captures(sys.argv[1] if len(sys.argv) > 1 else "V06")).most_common():
        print(n, key)
