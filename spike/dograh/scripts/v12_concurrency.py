"""V12: effective concurrency formula (offline) and the procedure for the live saturation test."""
import math
import sys

from _common import require_live


def effective_concurrency(carrier_channels: int, dograh_org_limit: int | None, server_capacity: int,
                          headroom: float = 0.1) -> int:
    """min of the independent ceilings, minus headroom. `dograh_org_limit=None` = not enforced for API triggers."""
    ceilings = [carrier_channels, server_capacity] + ([dograh_org_limit] if dograh_org_limit else [])
    return max(1, math.floor(min(ceilings) * (1 - headroom)))


if __name__ == "__main__":
    if len(sys.argv) == 4:
        print(effective_concurrency(int(sys.argv[1]), int(sys.argv[2]) or None, int(sys.argv[3])))
        sys.exit(0)
    print("usage: v12_concurrency.py CARRIER_CHANNELS DOGRAH_ORG_LIMIT(0=unenforced) SERVER_CAPACITY")
    require_live("V12", ["Set DEFAULT_ORG_CONCURRENCY_LIMIT=2 on a scratch instance",
                         "Trigger 3 short calls concurrently (needs 3 calls of budget); record the response of the 3rd",
                         "Record whether the 3rd is rejected (code/body), queued, or accepted (limit not applied to API triggers)",
                         "Read rate-limit headers on rapid get-run polling; ask the carrier for calls-per-second"])
