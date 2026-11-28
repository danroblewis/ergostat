"""The change-management fields of an impact report (SPEC §12n): what else a change touches, whether it writes, the
rollback, the risk level, the projections' confidence; and the report of a change to the model."""

from __future__ import annotations

import time

from ..spec.ir import DEAD, Spec
from . import closedloop as cl
from . import fit as ft
from . import observe as ob
from . import simulate as sim


class ImpactError(ValueError):
    pass


def ends(spec: Spec, refs) -> list[str]:
    """``refs`` and the stocks their flows move."""
    return list(dict.fromkeys([f"stock.{s}" for r in refs if r.startswith("flow.") and r[5:] in spec.flows
                               for s in (spec.flows[r[5:]].source, spec.flows[r[5:]].target) if s] + list(refs)))


def around(spec: Spec, refs, but: str | None = None) -> tuple[list[str], list[str]]:
    """The blocks that read ``refs`` or the stocks their flows move, or take items from those stocks (other than
    ``but``), and the goals on them."""
    moved = set(ends(spec, refs))
    held = {(z.items.get("kind"), st) for r in moved if r.startswith("stock.") and r[6:] in spec.stocks
            for z in spec.stocks[r[6:]].sensors.values() if z.items
            for st in (z.items.get("state") if isinstance(z.items.get("state"), list) else [z.items.get("state")])}
    reads = lambda o: any(str(r) in moved for r in o.reads()) or (o.takes and any((o.takes.kind, a) in held for a in o.takes.at))  # noqa: E731
    return (sorted(o.name for o in spec.blocks.values() if o.name != but and reads(o)),
            sorted(g.name for g in spec.goals.values() if str(g.of) in moved))


def touches(p, spec: Spec, block: str) -> dict:
    """What else the block touches, whether it writes, and the items of the projection it takes, by state."""
    b = spec.blocks[block]
    readers, goals = around(spec, {str(t) for t in b.targets() if t.kind == "flow"}, block)
    acts = [{"name": a, "gate": spec.actions[a].gate if a in spec.actions else "?"} for a in b.params.get("actions") or []]
    items = None
    if b.takes:
        from ..spec import items as its
        counts = (next((k for k in its.listing(p.events, spec, kind=b.takes.kind, n=1)["projections"] if k["name"] == b.takes.kind),
                       {}).get("counts") or {})
        items = {"projection": b.takes.kind, "states": {s: counts.get(s, 0) for s in b.takes.at}, "dead": counts.get(DEAD, 0)}
    return {"touches": {"blocks": readers, "goals": goals, "commands": sorted(t.name for t in b.targets() if t.kind in ("block", "goal")),
                        "actions": acts}, "read_only": not acts, "writes": [a["name"] for a in acts], "items": items}


def rollback(t: dict, commit: str | None, block: str) -> dict:
    how = f"git revert {commit}" if commit else "revert the fix's commit (git revert COMMIT)"
    it = t.pop("items")
    said = f"{how}: {block} fails again as before"
    if it:
        waiting = ", ".join(f"{n} in {s}" for s, n in it["states"].items())
        said += (f"; the {it['projection']} items it moved stay where they are, the ones it would take next wait ({waiting} now), "
                 f"and a run in flight gives its item back when its lease expires")
        if it["dead"]:
            said += (f". {it['dead']} {it['projection']} items are dead letters now (given up on after their attempts): the fix does "
                     f"not bring them back; redrive them once it is in (ergostat lease ITEM --redrive)")
    if t["writes"]:
        said += f"; what its actions did outside ({', '.join(t['writes'])}) is not undone by the revert"
    return {"how": how, "items": it, "said": said}


def risk_level(t: dict, tests: str | None) -> dict:
    acts = [(2 if a["gate"] == "auto" else 1, a["name"]) for a in t["touches"]["actions"] if a["gate"] in ("auto", "approve")]
    pts = sum(k for k, _ in acts)
    why = [f"it writes: {n} ({'runs without asking' if k == 2 else 'held for approval'})" for k, n in acts]
    radius = sum(len(t["touches"][k]) for k in ("blocks", "goals", "commands"))
    for k, said in ((1 if radius > 3 else 0, f"a blast radius of {radius} parts"), (1 if not tests else 0, "its tests were not run"),
                    (4 if tests == "failed" else 0, "its tests failed")):
        pts, why = pts + k, why + [said] if k else why
    return {"level": "low" if pts <= 1 else "medium" if pts <= 3 else "high", "why": why or ["reads only, a small radius, tested"]}


def confidence(spec: Spec, data: ob.Data, run: sim.Run, models: dict, refs: list[str], valid: bool) -> dict:
    """Each model the projection runs (identified, or assumed for want of record) and each charted stock's fit (R², skill
    against its mean); low, naming the worst part first, with a stock fitting worse than its mean, an assumed model or a
    projection not valid."""
    fit = ft.compare(spec, data, run) if run.valid else {"stocks": {}}
    parts = [{"ref": m.label or m.block, "how": "assumed" if m.assumed else "identified", "said": m.assumed or f"from {m.basis}"}
             for m in models.values()]
    stocks = [(r, s) for r in refs if (s := fit["stocks"].get(r)) and s.get("n") and not s.get("exact") and s.get("r2") is not None]
    parts += [{"ref": r, "how": "worse than its mean" if (s.get("skill") or 0) < 0 else "fits", "r2": s["r2"], "skill": s.get("skill")}
              for r, s in stocks]
    skills = sorted((s["skill"], r) for r, s in stocks if s.get("skill") is not None)
    assumed = [x for x in parts if x["how"] == "assumed"]
    worst = (f"the model fits {skills[0][1][6:]} worse than its mean (skill {skills[0][0]:.3g})" if skills and skills[0][0] < 0 else
             f"{assumed[0]['ref']}'s model is assumed ({assumed[0]['said']})" if assumed else
             None if valid else "the projection is not valid")
    level = "low" if worst else "high" if skills and skills[0][0] >= 0.5 else "medium"
    said = (f"low: {worst}" + (f" (and {len(assumed)} model{'s' if len(assumed) > 1 else ''} assumed)" if assumed and skills
                                and skills[0][0] < 0 else "") if worst else
            "high: every model identified, every stock it charts fits with skill 0.5 or more" if level == "high" else
            "medium: every model identified" + ("; not every stock it charts fits well" if skills else "; no stock it charts is fitted"))
    return {"level": level, "worst": worst, "parts": parts, "said": said}


def goal_rows(spec: Spec, cr: cl.ClosedRun, before: dict | None = None) -> dict:
    out = {}
    for name, g in spec.goals.items():
        e = cr.off_end.get(name) or []
        i = next((k for k, v in enumerate(e) if v), None)
        out[name] = {"of": str(g.of), "hold": str(g.hold), "off_at": cr.times[i] if i is not None else None, "off_before": (
            before or {}).get(name) == "off", "off_end": bool(e and e[-1]), "hours_off": round(cr.off_hours.get(name, 0.0), 4)}
    return out


def charts(spec: Spec, data: ob.Data, refs: list[str], without, with_) -> list[dict]:
    out = []
    for r in refs[:6]:
        kind, name = r.split(".", 1)
        part = spec.stocks.get(name) if kind == "stock" else spec.flows.get(name)
        g = next((g for g in spec.goals.values() if str(g.of) == r and g.hold.value is not None), None)
        out.append({"ref": r, "name": name, "kind": kind, "unit": getattr(part, "unit", "") or "", "per": kind == "flow",
                    "goal": {"value": g.hold.value, "setpoint": str(g.hold)} if g else None,
                    "measured": data.values.get(r) or [], "without": without.values.get(r), "with": with_.values.get(r) if with_ else None})
    return out


def change_report(p, spec: Spec, pid: str, data: ob.Data, run: sim.Run, at: float, began: float) -> dict:
    """A model change: what it touches, its forecast as the model is and with it, the goals' time off under both."""
    from . import proposals as pr
    from . import review as rv
    from . import trial as tr
    x = pr.stored(p)[pid]
    try:
        after = tr.spec_after(p, tr.edits_of(x))
        fc = rv.forecast(p, spec, after, [x], at)
    except tr.TrialError as e:
        raise ImpactError(f"{pid}: {e}") from None
    b, a = fc["before"], fc["after"]
    refs = ends(spec, [r for r in (x.get("parts") or []) if r.startswith(("stock.", "flow."))] or
                [str(g.of) for g in spec.goals.values() if g.of.kind == "stock"])
    goals = goal_rows(spec, b) if isinstance(b, cl.ClosedRun) else {}
    if isinstance(a, cl.ClosedRun):
        for g, y in goal_rows(after, a).items():
            goals.setdefault(g, y)["hours_off_fixed_now"] = y["hours_off"]
    readers, near = around(spec, set(refs))
    blocks = sorted({str(r)[6:] for r in x.get("parts") or [] if str(r).startswith("block.")} & set(spec.blocks) | set(readers))
    t = {"touches": {"blocks": blocks, "goals": near, "commands": [], "actions": []}, "read_only": True, "writes": []}
    conf = confidence(spec, data, run, getattr(b, "models", {}) or {}, refs, b.valid)
    out = {"kind": "change", "about": f"change {pid}", "at": at, "broken": None, "horizon": fc["horizon"],
           "times": data.grid.times(), "ptimes": b.times, "charts": charts(spec, data, refs, b, a), "goals": goals,
           "rollout": None, "notes": ["a change to the model revises its forecast, not the world: when it is accepted "
                                      "changes nothing the record will show, so no rollout time is tried"],
           "fields": {**t, "rollback": {"how": "revert the change's edit to the model (git revert its commit)", "items": None,
                                        "said": "revert the edit: the model and its forecast are as they were; the record is untouched"},
                      "risk": risk_level(t, "passed" if x.get("state") in ("reviewing", "passed", "accepted") else None), "confidence": conf},
           "stopped": None, "seconds": round(time.monotonic() - began, 3)}
    lead = f"Low confidence: {conf['worst']}. " if conf["level"] == "low" else ""
    said = (fc["predicts"] or {}).get("said") or "it changes nothing the model forecasts"
    out["said"] = f"{lead}{x.get('title') or pid}: {said}. Risk {out['fields']['risk']['level']}, confidence {conf['level']}."
    return out
