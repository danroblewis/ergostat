import random

from sim import now, say, world

with world({"stale": 2, "last_scan": now() - 3}) as w:
    merged = random.choice([0, 0, 1, 1, 2])
    w["stale"] += merged
    hours = max(now() - w["last_scan"], 0.1) / 3600
    w["last_scan"] = now()
    stale = w["stale"]
say(sensor="stale-scan", value=stale)
say(sensor="churn-meter", value=round(merged / hours, 1))   # merged changes per hour, since the last scan
