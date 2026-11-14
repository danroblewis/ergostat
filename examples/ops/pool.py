"""The worker pool: jobs arrive in bursts; the pool works through them at a rate set by the
autoscaler (how far the valve is open), and the workers' logs fill the disk."""
import math
import random

from sim import now, say, world

with world({"waiting": 10, "workers": 2, "t0": now(), "written": 0.0}) as w:
    phase = (now() - w["t0"]) / 40.0
    arriving = max(0, int(random.gauss(6 + 5 * math.sin(phase), 2)))
    w["waiting"] += arriving
    done = min(w["waiting"], w["workers"] * 2)
    w["waiting"] -= done
    w["written"] = w.get("written", 0.0) + done * 0.05
    say(sensor="queue-depth", value=w["waiting"])
    say(valve="process-jobs", amount=done, position=w["workers"])   # how far open: the workers running
