"""The behaviour test, headless: the plant and one policy's loops, stepped together for a horizon, with nothing
else running. It is the same code ergostat's blocks run (bin/coord.py), on the same clock, sampled as each loop's
sheet says; what ergostat's own projection cannot do yet is close the loops through the blocks' laws (SPEC §12b:
projection is open loop), so the closed-loop runs over thirty days are made here.

    python3 -m world.experiment [--policy harness|designed|both] [--days 30] [--seed 1] [--out run/experiment]

writes <out>/<policy>-<seed>.json: the hourly series and the logs (what was found, and when; each stall; each cut).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                    # run as a script, from anywhere: the example's own folder
    sys.path.insert(0, str(ROOT))

from world import policy as P  # noqa: E402
from world.plant import STEP, Plant, fresh  # noqa: E402


def snapshot(p: Plant) -> dict:
    """What is read each hour for the charts: the plant's stocks, the controllers' settings."""
    c = p.s["ctrl"]
    cv1, _ = p.escaped_share(7)
    return {"t": round(p.t, 3), "present": p.present(), "ready": len(p.ids("ready")),
            "proposed": len(p.ids("proposed")), "leased": p.running(), "stalled": p.stalled(),
            "reported": len(p.ids("reported")), "accepted": len(p.ids("accepted")),
            "dead": len(p.ids("dead-letter")), "declined": len(p.ids("declined")),
            "undiscovered": p.undiscovered(), "queue": len(p.s["owner"]["queue"]),
            "decisions": round(p.s["owner"]["decisions"], 2), "window": round(p.s["window"]["tokens"]),
            "lines": p.s["code"]["lines"], "features": p.s["code"]["features"], "cv8": round(p.cv8(), 4),
            "rules": sum(1 for x in p.s["corr"].values() if x["state"] == "rule"),
            "held": sum(1 for x in p.s["corr"].values() if x["state"] == "window"),
            "discipline": round(c.get("discipline", 1.0), 3), "h_star": c.get("h_star"),
            "mode": c.get("mode", "normal"), "cv1": round(cv1, 4),
            "oldest_silence": round(max((p.silence(r) for r in p.s["runs"]), default=0.0), 3),
            "direction": p.s["dir"]["k"]}


def run(policy: str, days: float = 30, seed: int = 1) -> dict:
    p = Plant(fresh(seed, policy))
    hours: list[dict] = []
    last = int(p.t)
    end = p.s["t_start"] + days * 24
    while p.t < end - 1e-9:
        p.step(STEP)
        for loop, (period, *_laws) in P.LOOPS.items():
            if P.due(p, loop, period):
                P.law(policy, loop)(p)
        p.s["feed"].clear()
        if int(p.t + 1e-9) > last:                     # each factory hour, on the hour
            last = int(p.t + 1e-9)
            hours.append(snapshot(p))
    return {"policy": policy, "seed": seed, "days": days, "hours": hours, "counts": p.s["m"], "log": p.s["log"],
            "dirs": p.s["dirs"], "corrections": p.s["corr"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="both")
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--seed", type=int, nargs="+", default=[1])
    ap.add_argument("--out", type=Path, default=ROOT / "run" / "experiment")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for seed in a.seed:
        for pol in (["harness", "designed", "designed/quality"] if a.policy == "both" else [a.policy]):
            r = run(pol, a.days, seed)
            (a.out / f"{pol.replace('/', '-no-')}-{seed}.json").write_text(json.dumps(r))
            print(f"{pol} seed {seed}: {summary(r)}", flush=True)
    return 0


def summary(r: dict) -> str:
    c: dict = {}
    for v in r["counts"].values():
        for k, x in v.items():
            c[k] = c.get(k, 0) + x
    found = r["log"].get("found", [])
    after = sorted(f[1] - f[0] for f in found if f[2] != "check")
    med = after[len(after) // 2] if after else 0
    st = r["log"].get("stalls", [])
    away = sorted(60 * (s[1] - s[0]) for s in st if not s[2])
    pres = sorted(60 * (s[1] - s[0]) for s in st if s[2])
    rw = c.get("lines-reworked", 0) / max(c.get("lines-added", 1), 1)
    return (f"accepted {c.get('accepted', 0):.0f}, escaped {c.get('escaped', 0):.0f}, caught {c.get('caught', 0):.0f}, "
            f"found by owner {c.get('found-by-owner', 0):.0f}/work {c.get('found-by-work', 0):.0f}/tests "
            f"{c.get('found-by-tests', 0):.0f}, median found after {med:.1f}h, reworked/added {rw:.3f}, "
            f"stalls away {len(away)} (median {away[len(away) // 2] if away else 0:.0f} min), present {len(pres)} "
            f"(median {pres[len(pres) // 2] if pres else 0:.0f} min), cuts {c.get('cuts', 0):.0f}, corrections "
            f"{c.get('corrections', 0):.0f} (repeats {c.get('repeats', 0):.0f}), rules {r['hours'][-1]['rules']}, "
            f"decisions waiting {r['hours'][-1]['decisions']}, cv8 {r['hours'][-1]['cv8']:.2f}, "
            f"pruned {len(r['log'].get('pruned', []))}, hidden runs {c.get('hidden-runs', 0):.0f}/{c.get('test-runs', 0):.0f}")


if __name__ == "__main__":
    sys.exit(main())
