"""V10: inspect artifact URLs on a finished run and download with the SSRF guard. Content is never saved.

Usage: v10_artifacts.py WORKFLOW_ID RUN_ID allowed_host[,allowed_host...]
"""
import sys
import time
from urllib.parse import urlsplit

from _common import require_live, save_evidence, utcnow
from artifact_download import DownloadRefused, download
from dograh_client import DograhClient

ARTIFACT_FIELDS = ("recording_url", "transcript_url", "recording_public_url", "transcript_public_url")


def describe_urls(run: dict) -> dict:
    return {f: (urlsplit(run[f]).netloc, urlsplit(run[f]).path.count("/")) for f in ARTIFACT_FIELDS if run.get(f)}


if __name__ == "__main__":
    require_live("V10", ["Finish one call; run immediately, then again after 10 min and after 24 h",
                         "Note hosts (-> DOGRAH_ALLOWED_ARTIFACT_HOSTS), content types, sizes, redirect behaviour, expiry",
                         "Negative test: add a wrong host to the call and confirm it is refused"])
    wf, run_id, hosts = int(sys.argv[1]), int(sys.argv[2]), set(sys.argv[3].split(","))
    run = DograhClient.from_env().get_run(wf, run_id).body
    out = {"at": utcnow(), "url_hosts_and_depth": describe_urls(run), "downloads": {}}
    for f in ARTIFACT_FIELDS:
        if run.get(f):
            t0 = time.monotonic()
            try:
                ctype, data = download(run[f], hosts)
                out["downloads"][f] = {"content_type": ctype, "bytes": len(data), "s": round(time.monotonic() - t0, 2)}
            except DownloadRefused as exc:
                out["downloads"][f] = {"refused": str(exc)}
    save_evidence("V10", "artifacts.json", out)
    print(out)
