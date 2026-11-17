"""Leverage: which flow, made faster, moves the goals most (SD Lab's leverage panel, SPEC §4.9 there, as it
was tested): each flow in turn sped up by a tenth, the projection run again to its horizon from the
state now, and the flows ranked by how far each moves the stocks and flows the goals hold, toward
them or away. A flow with an equation is sped up by multiplying it (1.1 × its equation); one that is
an input is held a tenth higher. What a controller's flow moves is left out of the projection, so it
is left out here too. Nothing is kept or changed."""

from __future__ import annotations

from dataclasses import replace

from ..spec import equation as eq
from ..spec.ir import Equation, Spec
from . import observe as ob
from . import simulate as sim

FASTER = 1.1
MOST = 60               # more flows than this: only the ones asked for


def _boosted(spec: Spec, data: ob.Data, flow: str) -> tuple[sim.Plan, ob.Data] | None:
    f = spec.flows[flow]
    ref = f"flow.{flow}"
    if f.equation is not None:
        text = f"{FASTER} * ({f.equation.text})"
        tree = eq.parse(text, spec.parameters)
        return sim.plan(spec, extra={ref: Equation(text, tree, eq.refs(tree), eq.names(tree))}), data
    vals = data.values.get(ref)
    if not vals or not any(v is not None for v in vals):
        return None
    d = replace(data, values={**data.values, ref: [None if v is None else v * FASTER for v in vals]})
    return sim.plan(spec), d


def _judged(spec: Spec) -> dict[str, list]:
    """Each part a goal holds, and the goals on it."""
    out: dict[str, list] = {}
    for g in spec.goals.values():
        out.setdefault(f"{g.of.kind}.{g.of.name}", []).append(g)
    return out


def toward(g, before: float, after: float) -> float:
    """How much closer to holding its goal (+) or further (−), as a share of where it was."""
    size = max(abs(before), abs(g.hold.value), 1e-9)
    if g.hold.op in ("<=", "<"):
        return (before - after) / size
    if g.hold.op in (">=", ">"):
        return (after - before) / size
    return (abs(before - g.hold.value) - abs(after - g.hold.value)) / size


def rank(spec: Spec, data: ob.Data, run: sim.Run, horizon: float, points: int = 24, flows: list[str] | None = None) -> dict:
    """The flows ranked by how far a tenth faster moves the goals at the horizon: each with its change to
    each goal's part (before, after, and toward the goal or away, as a share), and its score (the mean of
    those shares; + is toward the goals)."""
    judged = _judged(spec)
    if not judged:
        return {"goals": [], "rows": [], "horizon": horizon, "said": "no goal: leverage is how far a flow moves a goal"}
    base_pl = sim.plan(spec)
    base = sim.project(spec, data, run, horizon, base_pl, points=points)
    held = sim.controlled(spec)
    names = flows if flows is not None else [n for n in spec.flows if f"flow.{n}" not in held][:MOST]
    rows = []
    for name in names:
        if name not in spec.flows or f"flow.{name}" in held:
            continue
        got = _boosted(spec, data, name)
        if got is None:
            continue
        pl, d = got
        proj = sim.project(spec, d, run, horizon, pl, points=points)
        effect = {}
        for ref, gs in judged.items():
            b, a = (base.values.get(ref) or [None])[-1], (proj.values.get(ref) or [None])[-1]
            if b is None or a is None:
                continue
            for g in gs:
                effect[g.name] = {"part": ref, "before": b, "after": a, "toward": toward(g, b, a)}
        if effect:
            rows.append({"flow": name, "effect": effect, "score": sum(x["toward"] for x in effect.values()) / len(effect)})
    rows.sort(key=lambda r: -abs(r["score"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"goals": sorted({g for r in rows for g in r["effect"]}), "rows": rows, "horizon": horizon, "of": len(rows)}


def said(row: dict, of: int) -> str:
    """A flow's leverage in words: its rank, and what a tenth faster does to each goal it moves."""
    bits = []
    for g, x in sorted(row["effect"].items(), key=lambda kv: -abs(kv[1]["toward"])):
        if abs(x["toward"]) < 5e-4:
            continue
        bits.append(f"{x['part'].split('.', 1)[1]} {x['toward']:+.1%} {'toward' if x['toward'] > 0 else 'away from'} goal {g}")
    if not bits:
        return f"a tenth faster, {row['flow']} moves no goal (ranks {row['rank']} of {of})"
    return f"a tenth faster, {row['flow']} moves " + ", ".join(bits[:3]) + f" (ranks {row['rank']} of {of} flows)"
