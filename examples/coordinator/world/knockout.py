"""Loop knockout, sensitivity and integration-error tests (Sterman ch. 21; 00-oracle SD-14 to SD-17): the designed
Coordinator with one loop at a time put back to the harness's law, the conclusions under plausible changes to the
plant's uncertain numbers, and the results at half the time step.

    python3 -m world.knockout [--seeds 5] [--days 30]

prints three Markdown tables.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world import plant  # noqa: E402
from world.experiment import lead, run  # noqa: E402

KNOCKOUTS = [("designed", "the design, every loop in"), ("designed/acceptance", "LP1 out (the harness's check)"),
             ("designed/quality", "LP2 out (h* held at 0.1)"), ("designed/dispatch", "LP3 out (fan-out by pressure)"),
             ("designed/watchdog", "LP5 out (no lease)"), ("designed/admission", "LP6 out (everything admitted)"),
             ("designed/attention", "LP7's report out"), ("designed/externalise", "LP9 out"),
             ("designed/consolidation", "LP10 out"), ("harness", "the harness as it was")]

SENSITIVITY = [("as calibrated", {}), ("discovery twice as slow", {"DISCOVERY": {"fast": 1.5, "work": 0.0175, "owner": 0.035}}),
               ("discovery twice as fast", {"DISCOVERY": {"fast": 1.5, "work": 0.07, "owner": 0.14}}),
               ("stalls twice as likely", {"P_STALL": 0.24}), ("a new direction twice as bad", {"PEAK": 0.9}),
               ("long silences in sound runs, 3 times as often", {"QUIET_RATE": 0.3})]


def measures(r: dict) -> dict:
    c: dict = {}
    for v in r["counts"].values():
        for k, x in v.items():
            c[k] = c.get(k, 0) + x
    st = r["log"].get("stalls", [])
    away = [60 * (s[1] - s[0]) for s in st if not s[2]]
    found = r["log"].get("found", [])
    return {"escaped": c.get("escaped", 0) / max(c.get("accepted", 1), 1),
            "caught": c.get("caught", 0) / max(len(found), 1),
            "stall": statistics.median(away) if away else 0.0, "stall-max": max(away) if away else 0.0,
            "hidden": c.get("hidden-runs", 0) / max(c.get("test-runs", 1), 1),
            "decisions": r["hours"][-1]["decisions"], "blockers": max(q["queue"] for q in r["hours"]),
            "cv8": max(q["cv8"] for q in r["hours"]), "pruned": len(r["log"].get("pruned", [])),
            "repeats": c.get("repeats", 0), "lead": lead(r), "false": c.get("false-expiries", 0)}


def med(rs: list[dict], k: str) -> float:
    return statistics.median(m[k] for m in rs)


COLS = [("escaped", "escaped / accepted", "{:.3f}"), ("caught", "caught before landing", "{:.2f}"),
        ("stall", "stall noticed away, median min", "{:.0f}"), ("stall-max", "longest", "{:.0f}"),
        ("hidden", "exit status unread", "{:.2f}"), ("blockers", "most blockers open", "{:.0f}"),
        ("decisions", "decisions waiting, day 30", "{:.0f}"), ("cv8", "highest CV8", "{:.2f}"),
        ("pruned", "owner prunes", "{:.0f}"), ("repeats", "repeated corrections", "{:.0f}"),
        ("lead", "hours to 90% of a direction", "{:.0f}"), ("false", "sound runs expired", "{:.0f}")]


def table(rows: list[tuple[str, list[dict]]], first: str) -> None:
    print(f"| {first} | " + " | ".join(c[1] for c in COLS) + " |")
    print("|---" * (len(COLS) + 1) + "|")
    for name, rs in rows:
        print(f"| {name} | " + " | ".join(f.format(med(rs, k)) for k, _, f in COLS) + " |")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--days", type=float, default=30)
    a = ap.parse_args()
    seeds = range(1, a.seeds + 1)
    print(f"Loop knockout ({a.seeds} seeds, medians)\n")
    table([(label, [measures(run(pol, a.days, s)) for s in seeds]) for pol, label in KNOCKOUTS], "policy")
    print(f"\nSensitivity ({a.seeds} seeds, medians): harness / designed\n")
    rows = []
    for label, change in SENSITIVITY:
        was = {k: getattr(plant, k) for k in change}
        for k, v in change.items():
            setattr(plant, k, v)
        try:
            rows.append((f"{label}, harness", [measures(run("harness", a.days, s)) for s in seeds]))
            rows.append((f"{label}, designed", [measures(run("designed", a.days, s)) for s in seeds]))
        finally:
            for k, v in was.items():
                setattr(plant, k, v)
    table(rows, "plant")
    print(f"\nIntegration error ({a.seeds} seeds, medians): the step halved\n")
    rows = []
    for step in (plant.STEP, plant.STEP / 2):
        was = plant.STEP
        plant.STEP = step
        import world.experiment as ex
        ex.STEP = step
        try:
            for pol in ("harness", "designed"):
                rows.append((f"{pol}, step {60 * step:.0f} min", [measures(run(pol, a.days, s)) for s in seeds]))
        finally:
            plant.STEP = was
            ex.STEP = was
    table(rows, "step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
