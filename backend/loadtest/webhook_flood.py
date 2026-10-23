"""Outage-shaped webhook flood for staging (Load Test Plan §4.3): python webhook_flood.py URL ATTEMPT_ID_FILE N CONCURRENCY.
The secret comes from DOGRAH_WEBHOOK_SECRET; ATTEMPT_ID_FILE lists one real staging attempt id per line."""
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

import requests

url, ids_file, n, workers = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
ids = open(ids_file).read().split()
headers = {"X-Dograh-Webhook-Secret": os.environ["DOGRAH_WEBHOOK_SECRET"]}


def send(i):
    t = time.monotonic()
    r = requests.post(url, json={"attempt_id": ids[i % len(ids)], "run_id": f"flood-{uuid.uuid4()}"}, headers=headers, timeout=10)
    return r.status_code, time.monotonic() - t


with ThreadPoolExecutor(workers) as pool:
    results = list(pool.map(send, range(n)))
lat = sorted(t for _, t in results)
print(Counter(c for c, _ in results), f"p50={lat[len(lat) // 2]:.3f}s p99={lat[int(len(lat) * .99) - 1]:.3f}s")
