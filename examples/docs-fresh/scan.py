"""The doc scanner: two sensors.

    python3 scan.py stale     how many pages are older than the code they describe; and each page
                              newly stale since it last looked (page.stale, page/api/auth.md)
    python3 scan.py churn     merged changes per hour, since the last time it looked
"""
import json
import sys
import time

from sim import START, world

with world({**START, "counted": 0, "last_scan": time.time() - 3}) as w:
    if sys.argv[1] == "stale":
        new = [p for p in w["stale"] if p not in w["reported"]]
        w["reported"] = list(w["stale"])
        for page in new:
            print(json.dumps({"event": "page.stale", "item": f"page/{page}", "data": {"change": w["stale"][page], "pr": None}}))
        print(len(w["stale"]))
    else:
        hours = max(time.time() - w["last_scan"], 0.1) / 3600
        print(round((w["merged"] - w["counted"]) / hours, 1))
        w["counted"], w["last_scan"] = w["merged"], time.time()
