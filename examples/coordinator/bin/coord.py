"""One loop of the Coordinator, run by its block: the world advanced to now, the loop's law applied once (the
policy is COORD_POLICY: the designed architecture by default, or `harness`, the harness as it was), and what it
moved reported to ergostat on the block's outputs.

    python3 bin/coord.py LOOP        (dispatch, acceptance, watchdog, admission, attention, externalise,
                                      quality, consolidation)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                         # the simulated world (world/), a folder of this example

from world import policy as P  # noqa: E402
from world import sim  # noqa: E402

# each loop's result, by name: the block's output it goes to
OUTPUTS = {
    "dispatch": {"leased": "flow.leased"},
    "acceptance": {"accepted": "flow.accepted", "rejected": "flow.rejected", "asked": "flow.asked",
                   "habit": "flow.habit-changed"},
    "watchdog": {"expired": "flow.expired", "dead-lettered": "flow.dead-lettered", "redriven": "flow.redriven"},
    "admission": {"admitted": "flow.admitted", "declined": "flow.declined"},
    "attention": {"handover": None},
    "externalise": {"externalised": "flow.externalised", "retired": "flow.retired"},
    "quality": {"allowance": None},
    "consolidation": {"mode": "flow.mode-switched"},
}


def main() -> int:
    loop = sys.argv[1]
    with sim.advanced() as p:
        before = p.s["owner"]["decisions"]
        habit = p.s["ctrl"].get("discipline", 0.0) if sim.POLICY.startswith("harness") else 1.0
        got = P.law(sim.POLICY, loop)(p)
        if loop == "acceptance":                      # the checking habit, as the check practised it (B4)
            now = p.s["ctrl"].get("discipline", 0.0) if sim.POLICY.startswith("harness") else 1.0
            got["habit"] = round(now - habit, 4)
        h_star = p.s["ctrl"].get("h_star")
        confirmed = before - p.s["owner"]["decisions"]
    for name, n in got.items():
        out = OUTPUTS[loop].get(name)
        if out:
            print(json.dumps({"out": out, "moved": n}))
    if loop == "attention":                           # the handover report: the decisions it put to the owner
        print(json.dumps({"out": "flow.decisions-confirmed", "moved": round(max(confirmed, 0.0), 2)}))
    if loop == "quality" and h_star is not None:      # LP2 sets LP1's setpoint (the cascade)
        print(json.dumps({"out": "goal.hidden-rework-allowed", "value": round(h_star, 4)}))
    print(json.dumps({"decision": f"{loop} ({sim.POLICY})", "why": json.dumps(got)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
