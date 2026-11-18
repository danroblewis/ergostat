"""What a sensor reads from the world: one number, as a real deployment would read it from the tracker, git, the
harness's usage records or the owner's last act. `undiscovered` is the exception: no deployment can read it (it is
what x̂4 estimates); the simulation shows its truth so the estimate can be judged.

    python3 world/read.py NAME          (rate:COUNTER is that counter per hour of ergostat's clock, over 10 minutes)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world import policy as P  # noqa: E402
from world import sim  # noqa: E402
from world.plant import CATCH, Plant  # noqa: E402

WINDOW = 600.0                                    # seconds of ergostat's clock a rate is taken over


def rate(p: Plant, counter: str) -> float:
    """A counter of the world's per hour of ergostat's own clock, over the last ten minutes of it."""
    span = WINDOW / sim.HOUR                      # factory hours
    t0 = p.t - span
    n = 0.0
    for h in range(int(t0), int(p.t) + 1):
        v = p.s["m"].get(str(h), {}).get(counter, 0)
        lo, hi = max(t0, h), min(p.t, h + 1)
        if hi > lo:
            n += v * (hi - lo) if h < int(p.t) else v * min(1.0, (hi - lo) / max(p.t - h, 1e-9))
    return n * 3600 / WINDOW


def x4_accepted(p: Plant) -> float:
    """x̂4 for the work accepted over the last factory day: the hidden rework the observer expects of it, at the
    depth each was checked (the mean, per item; 0 when nothing was accepted)."""
    xs = []
    for it in p.s["items"].values():
        if it.get("landed", -1e9) >= p.t - 24 and it["state"] == "accepted" and it["origin"] != "removal":
            d = it.get("depth_checked", "tests")
            xs.append(P.escapes(P.x4(p, it), d) if d in CATCH else 0.0)
    return sum(xs) / len(xs) if xs else 0.0


def cv2(p: Plant) -> float:
    """CV2: of the rework found over the last week, the share found at or before acceptance."""
    found = [f for f in p.s["log"].get("found", []) if f[1] >= p.t - 7 * 24]
    return sum(1 for f in found if f[2] == "check") / len(found) if found else 0.0


def hidden(p: Plant) -> float:
    """Of the test runs over the last factory day, the share whose exit status was not read."""
    runs = hid = 0.0
    for h in range(int(p.t) - 24, int(p.t) + 1):
        m = p.s["m"].get(str(h), {})
        runs += m.get("test-runs", 0)
        hid += m.get("hidden-runs", 0)
    return hid / runs if runs else 0.0


def value(name: str) -> float:
    with sim.advanced() as p:
        s = p.s
        if name.startswith("rate:"):
            return rate(p, name[5:])
        return {
            "oldest-silence": lambda: max((p.silence(r) for r in s["runs"]), default=0.0),
            "undiscovered": lambda: p.undiscovered(),
            "x4": lambda: x4_accepted(p),
            "cv1": lambda: p.escaped_share(7)[0],
            "cv2": lambda: cv2(p),
            "hidden": lambda: hidden(p),
            "habit": lambda: s["ctrl"].get("discipline", 0.0) if s["policy"].startswith("harness") else 1.0,
            "direction-age": lambda: p.t - s["dirs"][-1] if s["dirs"] else 0.0,
            "code": lambda: s["code"]["lines"],
            "features": lambda: s["code"]["features"],
            "mode": lambda: 1.0 if s["ctrl"].get("mode") == "consolidation" else 0.0,
            "cv8": lambda: p.cv8(),
            "present": lambda: 1.0 if p.present() else 0.0,
            "pool-cap": lambda: float(P.CAP),
            "queue": lambda: len(s["owner"]["queue"]),
            "decisions": lambda: round(s["owner"]["decisions"], 2),
            "window": lambda: s["window"]["tokens"] if s["window"].get("on") else
            max((r["tokens"] for r in s["runs"].values()), default=0.0),
            "rules": lambda: sum(1 for c in s["corr"].values() if c["state"] == "rule"),
            "held": lambda: sum(1 for c in s["corr"].values() if c["state"] == "window"),
        }[name]()


if __name__ == "__main__":
    print(round(float(value(sys.argv[1])), 4))
