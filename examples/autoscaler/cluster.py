"""A made-up cluster: one deployment (web), its load, and a horizontal pod autoscaler that ergostat does not run.

The world moves on wall-clock time, a second a tick, whenever anything reads it (.sim.json, under a lock). The
autoscaler is the Kubernetes HPA's documented rule: every SYNC seconds desired = ceil(replicas × utilisation /
target), nothing within the tolerance (10%), scale-up at most max(100%, +4 pods) a sync, scale-down to the highest
recommendation of the stabilisation window, within [MIN, MAX]. New pods take READY seconds to take load. Its windows
are a third of the defaults (sync 15s, stabilisation 300s) so a demo shows a few minutes of scaling in one.

What it exposes is what a cluster does, and nothing of the rule:

    python3 cluster.py replicas      the deployment's replicas (kube_deployment_spec_replicas)
    python3 cluster.py utilisation   CPU used over requested, averaged over the ready pods (the HPA's own metric)
    python3 cluster.py load          CPU in use, in cores (container_cpu_usage, summed)
    python3 cluster.py events        its scaling events as JSON lines (kubectl get events: SuccessfulRescale)
"""
import fcntl
import json
import math
import random
import sys
import time
from pathlib import Path

PATH = Path(".sim.json")
TARGET, TOLERANCE, MIN, MAX = 0.6, 0.1, 2, 20
SYNC, WINDOW, READY = 5, 100, 10        # seconds: the HPA's sync period, its scale-down stabilisation, a pod's start
COST = 0.02                             # CPU seconds a request


def requests(t: float) -> float:
    """Requests a second: a slow swell, a faster wave, noise (seeded by the second, so any reader sees the same)."""
    return max(0.0, 260 + 160 * math.sin(2 * math.pi * t / 900) + 70 * math.sin(2 * math.pi * t / 170)
               + random.Random(int(t)).gauss(0, 15))


def fresh(t: float) -> dict:
    return {"t": t, "replicas": 6, "ready": 6, "starting": [], "recs": [], "next_sync": t, "seq": 0, "events": []}


def tick(s: dict, t: float) -> None:
    s["t"] = t
    s["ready"] += sum(n for at, n in s["starting"] if at <= t)
    s["starting"] = [[at, n] for at, n in s["starting"] if at > t]
    s["ready"] = min(s["ready"], s["replicas"])
    s["load"] = requests(t) * COST
    s["util"] = s["load"] / max(1, s["ready"])
    if t < s["next_sync"]:
        return
    s["next_sync"] = t + SYNC
    cur = s["replicas"]
    ratio = s["util"] / TARGET
    desired = cur if abs(ratio - 1) <= TOLERANCE else math.ceil(cur * ratio)
    s["recs"] = [[at, d] for at, d in s["recs"] if at > t - WINDOW] + [[t, desired]]
    if desired < cur:
        desired = max(d for _, d in s["recs"])          # the stabilisation window: the highest it recommended
    new = max(MIN, min(MAX, desired, max(2 * cur, cur + 4)))
    if new == cur:
        return
    if new > cur:
        s["starting"].append([t + READY, new - cur])
    else:
        s["ready"] = min(s["ready"], new)
    s["replicas"], s["seq"] = new, s["seq"] + 1
    why = "above" if new > cur else "below"
    s["events"] = s["events"][-199:] + [{"seq": s["seq"], "id": f"web-hpa-{s['seq']}", "time": round(t, 1),
                                         "reason": "SuccessfulRescale", "replicas": new,
                                         "message": f"New size: {new}; reason: cpu resource utilization above target"
                                         if why == "above" else f"New size: {new}; reason: All metrics below target"}]


def advance(s: dict, now: float) -> dict:
    """The world from where it was to now, a second at a time (a gap of over an hour starts again, its events' numbers
    going on from where they were, as a collector's cursor expects)."""
    if not s or now - s["t"] > 3600:
        s = {**fresh(now - 1), "seq": (s or {}).get("seq", 0)}
    while s["t"] + 1 <= now:
        tick(s, s["t"] + 1)
    return s


def main(what: str) -> None:
    with open(".sim.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = advance(json.loads(PATH.read_text()) if PATH.exists() else {}, time.time())
        PATH.write_text(json.dumps(s))
    if what == "events":
        for e in s["events"]:
            print(json.dumps(e))
    else:
        print(round({"replicas": s["replicas"], "utilisation": s.get("util", 0.0), "load": s.get("load", 0.0)}[what], 4))


if __name__ == "__main__":
    main(sys.argv[1])
