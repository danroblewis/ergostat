"""What the modelling loop is doing, or waiting for, in one sentence (SPEC §12e): never silent. ``ergostat status``
and the Model page say it. Cheap: it reads the record (the model-error stock's last reading, the requests, the tiers'
last runs, the changes waiting), and replays nothing."""

from __future__ import annotations

import time

from ..durations import human as dur


def _last_run(p, block: str) -> float | None:
    got = p.events.query(n=1, item=block, type="agent.ran")
    return got[-1]["time"] if got else None


def of(p, now: float | None = None) -> dict:
    """``{"on", "fit", "fit_holds", "fit_why", "requests", "tiers", "waiting", "says"}``."""
    from . import proposals as pr
    from . import requests as rq
    spec = p.model.spec
    now = now or time.time()
    if not any(b.type == "judge" for b in spec.blocks.values()):
        return {"on": False, "says": "modelling is not in the model: add uses: {modelling: {use: modelling}}"}
    fit, holds, why = None, None, None
    st = spec.stocks.get("model-error")
    goal = spec.goals.get("model-fits")
    if st is not None:
        for s in st.sensors.values():
            got = p.measurements.latest(s.series, now)
            if got and now - got[0] < 3 * max(s.every or 60.0, 60.0):
                fit = got[1]
    reqs = rq.stored(p)
    unknown = next((r for r in reqs.values() if r.get("code") == "fit-unknown" and r["state"] != "answered"), None)
    if fit is None:
        why = (unknown or {}).get("says") or "the model's fit has not been read yet"
    elif goal is not None:
        holds = not goal.hold.outside(fit, goal.tolerance)
    counts = {s: 0 for s in ("open", "proposed", "held", "answered")}
    for r in reqs.values():
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    tiers = {}
    for name in ("fixer", "modeller", "improver"):
        b = spec.blocks.get(name)
        if b is not None:
            tiers[name] = {"every": b.every, "last": _last_run(p, name)}
    waiting = [x for x in pr.pending(p, spec)]
    owner = [x for x in waiting if x["state"] == "passed" or x.get("kind") in ("control", "measurement")]
    held_ai = [r for r in reqs.values() if r["state"] == "held" and r.get("tier") == "ai"]
    parts = []
    if fit is None:
        parts.append(f"fit unknown ({why.split(': ', 1)[-1][:160]})")
    else:
        parts.append(f"fit {fit:.3g}" + ("" if holds is None else (" holding" if holds else " off its goal")))
    open_ = counts["open"] + counts["proposed"] + counts["held"]
    if open_:
        parts.append(f"{open_} request{'s' if open_ != 1 else ''} unanswered ({counts['open']} open, {counts['proposed']} "
                     f"with a change waiting, {counts['held']} held)")
    if "fixer" in tiers and counts["open"]:
        t = tiers["fixer"]
        parts.append("the rule tier " + (f"ran {dur(now - t['last'])} ago" if t["last"] else "has not run yet")
                     + (f", every {dur(t['every'])}" if t["every"] else ""))
    if held_ai:
        parts.append(f"{len(held_ai)} held for the AI tier" + ("" if "modeller" in tiers else ", which is off (ai: true turns it on)"))
    if owner:
        parts.append(f"{len(owner)} change{'s' if len(owner) != 1 else ''} waiting for the owner (the Model page's review queue)")
    if waiting and len(waiting) > len(owner):
        parts.append(f"{len(waiting) - len(owner)} with the judge")
    if "redesigner" in spec.blocks:                      # the structural review, on its own or asked: its last run
        from . import redesign as rd
        last = rd.last(p)
        if last:
            parts.append(f"the redesigner last reviewed {last['system']} {dur(now - last['at'])} ago"
                         + (f" ({last['trigger']})" if last.get("trigger") else "") + f": {last['result']}")
    if not open_ and not waiting and (fit is None or holds is not False):
        parts.append("nothing to do: every request answered" + ("" if fit is None else " and the fit holds"))
    return {"on": True, "fit": fit, "fit_holds": holds, "fit_why": why, "requests": counts, "tiers": tiers,
            "waiting": {"judge": len(waiting) - len(owner), "owner": len(owner)}, "says": "; ".join(parts)}
