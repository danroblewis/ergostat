"""The doc scanner: two sensors.

    python3 scan.py stale     how many pages are older than the code they describe
    python3 scan.py churn     merged changes per hour, since the last time it looked
"""
import sys
import time

from sim import START, world

with world({**START, "counted": 0, "last_scan": time.time() - 3}) as w:
    if sys.argv[1] == "stale":
        print(w["stale"])
    else:
        hours = max(time.time() - w["last_scan"], 0.1) / 3600
        print(round((w["merged"] - w["counted"]) / hours, 1))
        w["counted"], w["last_scan"] = w["merged"], time.time()
