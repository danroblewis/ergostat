"""Which feedback loops drive the behaviour, and when: loop dominance by the Loops That Matter method
(Schoenberg, Davidsen and Eberlein, "Understanding model behavior using the Loops that Matter method",
*System Dynamics Review* 36(2), 2020; Eberlein and Schoenberg, "Finding the loops that matter", 2020).

Over each step of the replay, every link in a loop is given a **link score**: how much of the change
in its effect came from the change in its cause, with the link's sign.

- a flow into or out of a stock: the flow's change over the change in the stock's net flow, ±|Δflow /
  Δnet| (the stock's own structure, so its sign is the flow's: + in, − out);
- a cause of a part the model works out by an equation: |Δₓz / Δz| · sign(Δₓz / Δx), where Δₓz is how
  much the equation's value changes when only that cause changes (the others held where they were);
- a cause of a part with exactly one cause and no equation (a goal's error, a decision with one input,
  a measured flow the model says one thing drives): all of its change, its sign as drawn (1, or 0 when
  it did not change).

A loop's score is the product of its links' scores; its **relative score**, its score over the sum of
every scored loop's |score| at that step, says how much of the behaviour it explains then, from −1 (a
balancing loop driving everything) to +1 (a reinforcing one). The loop with the largest |relative
score| dominates that step. A loop through a link that cannot be scored (a decision with several
inputs whose response the model does not write, an equation with a delay inside it, an unsigned link)
is said to be not scored, with why; the relative scores are of the loops scored. All of this is read
from the replay on the page's grid and the record beside it: what the model says, where it says it."""

from __future__ import annotations

from ..spec import causal
from ..spec import equation as eq
from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim


def _value(run: sim.Run, data: ob.Data, held: dict, ref: str, i: int) -> float | None:
    if ref in run.values:
        v = run.values[ref][i]
        if v is not None:
            return v
    if ref not in held:
        held[ref] = data.held(ref) if ref in data.values else None
    got = held[ref]
    return got[i] if got else None


def scorer(spec: Spec, pl: sim.Plan) -> tuple[dict[tuple[str, str], str], dict[str, int]]:
    """How each link is scored (``material``, ``equation``, ``single``), or why it cannot be (``why:…``)."""
    ls = causal.links(spec)
    into: dict[str, int] = {}
    for x in ls:
        into[x.target] = into.get(x.target, 0) + 1
    how = {}
    for x in ls:
        if x.sign is None:
            how[(x.source, x.target)] = f"why:its link from {x.source} to {x.target} has no sign"
        elif x.kind == "material":
            how[(x.source, x.target)] = "material"
        elif x.target in pl.eqs:
            how[(x.source, x.target)] = ("equation" if not pl.eqs[x.target].slots else
                                         f"why:{x.target}'s equation has a delay inside it (its hidden stocks are not links of the loop)")
        elif into.get(x.target) == 1:
            how[(x.source, x.target)] = "single"
        else:
            what = "a decision" if x.target.startswith("block.") else "a part"
            how[(x.source, x.target)] = (f"why:{x.target} is {what} with {into[x.target]} inputs and no equation, so how much of its "
                                         f"change comes from each is not written")
    return how, into


def dominance(spec: Spec, data: ob.Data, run: sim.Run, pl: sim.Plan | None = None) -> dict:
    """Each loop's relative score at each bucket (None where nothing changed), which loop dominates
    each bucket, and for each loop not scored, why."""
    pl = pl or sim.plan(spec)
    loops = causal.loops(spec)
    how, _ = scorer(spec, pl)
    n = data.grid.n
    held: dict = {}
    nets: dict[str, list[float | None]] = {}

    def net(stock: str, i: int) -> float | None:
        if stock not in nets:
            fs = spec.flows_of(stock)
            vals = []
            for j in range(n):
                tot = 0.0
                for f in fs:
                    v = _value(run, data, held, f"flow.{f.name}", j)
                    if v is None:
                        tot = None
                        break
                    tot += v if f.target == stock else -v
                vals.append(tot)
            nets[stock] = vals
        return nets[stock][i]

    def changed(ref: str, i: int) -> float | None:
        a, b = _value(run, data, held, ref, i - 1), _value(run, data, held, ref, i)
        return None if a is None or b is None else b - a

    def partial(src: str, dst: str, i: int) -> float | None:
        c = pl.eqs[dst]
        refs = eq.refs(c.tree)
        before = {r: _value(run, data, held, r, i - 1) for r in refs}
        if any(v is None for v in before.values()):
            return None
        now = dict(before)
        now[src] = _value(run, data, held, src, i)
        if now[src] is None:
            return None
        after_all = {r: _value(run, data, held, r, i) for r in refs}
        if any(v is None for v in after_all.values()):
            return None
        try:
            y0 = c.fn(before, pl.params, [], [], True)
            dz = c.fn(after_all, pl.params, [], [], True) - y0
            dxz = c.fn(now, pl.params, [], [], True) - y0
        except (ArithmeticError, ValueError):
            return None
        dx = now[src] - before[src]
        if not dz or not dx:
            return 0.0
        return abs(dxz / dz) * (1 if dxz / dx > 0 else -1 if dxz / dx < 0 else 0)

    def score(x: causal.Link, i: int) -> float | None:
        kind = how[(x.source, x.target)]
        if kind == "material":
            d, a, b = changed(x.source, i), net(x.target[6:], i - 1), net(x.target[6:], i)
            if d is None or a is None or b is None:
                return None
            return 0.0 if b == a else x.sign * abs(d / (b - a))
        if kind == "equation":
            return partial(x.source, x.target, i)
        if kind == "single":                             # what is not measured (a goal's error, a decision) passes it on
            d = changed(x.target, i) if measured(x.target) else 1.0
            return None if d is None else (0.0 if not d else float(x.sign))
        return None

    def measured(ref: str) -> bool:
        return ref in run.values or any(v is not None for v in data.values.get(ref) or [])

    scored, why = [], {}
    for lp in loops:
        bad = next((how[(x.source, x.target)][4:] for x in lp.links if how[(x.source, x.target)].startswith("why:")), None)
        if bad:
            why[lp.name] = bad
        else:
            scored.append(lp)
    raw: dict[str, list[float | None]] = {lp.name: [None] * n for lp in scored}
    for i in range(1, n):
        for lp in scored:
            s = 1.0
            for x in lp.links:
                v = score(x, i)
                if v is None:
                    s = None
                    break
                s *= v
            raw[lp.name][i] = s
    rel: dict[str, list[float | None]] = {k: [None] * n for k in raw}
    top: list[str | None] = [None] * n
    for i in range(n):
        tot = sum(abs(v[i]) for v in raw.values() if v[i] is not None)
        if not tot:
            continue
        best, size = None, 0.0
        for k, v in raw.items():
            if v[i] is not None:
                rel[k][i] = v[i] / tot
                if abs(rel[k][i]) > size:
                    best, size = k, abs(rel[k][i])
        top[i] = best
    steps = sum(1 for t in top if t)
    share = {k: (sum(1 for t in top if t == k) / steps if steps else None) for k in raw}
    return {"times": data.grid.times(), "relative": rel, "dominant": top, "share": share, "not_scored": why,
            "polarity": {lp.name: lp.polarity for lp in loops}, "steps": steps}
