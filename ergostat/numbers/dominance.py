"""Which feedback loops drive the behaviour, and when: loop dominance by the Loops That Matter method
(Schoenberg, Davidsen and Eberlein, "Understanding model behavior using the Loops that Matter method",
*System Dynamics Review* 36(2), 2020; Eberlein and Schoenberg, "Finding the loops that matter", 2020).

Computed on the simulation itself, at its integration step (the replay, with every part along a scored
loop traced at each step: ``simulate.replay(trace=…)``), from the model's own values: what the replay
integrates and works out, and the inputs it was driven by. Over each step every link in a loop is given a
**link score**: how much of the change in its effect came from the change in its cause, with the link's sign.

- a flow into or out of a stock: the flow's change over the change in the stock's net flow, ±|Δflow /
  Δnet| (the stock's own structure, so its sign is the flow's: + in, − out);
- a cause of a part the model works out by an equation: |Δₓz / Δz| · sign(Δₓz / Δx), where Δₓz is how
  much the equation's value changes when only that cause changes (the others held where they were);
- a cause of a part with exactly one cause and no equation: all of its change, with its sign, when the
  part changed (or, for a part the run has no value for, a goal's error or a decision, when its cause
  changed: an **assumed** link, said as such, since the model does not write how it answers); 0 when it
  did not.

A loop's score is the product of its links' scores. Its **relative score** is taken **per stock**, as LTM
does: its score over the sum of the |scores| of the scored loops through that stock, from −1 (a balancing
loop drives everything at the stock) to +1 (a reinforcing one). Loops in structures that share no stock
are never weighed against each other: one metric's smoothing never drives another's. Each display bucket
gets the mean of its steps' relative scores; the loop with the largest |relative score| at a stock
**dominates** it then, unless two are tied (none is named) or a loop through the stock cannot be scored
(none is named, since an unscored loop may be the one that drives it: the share of the stock's loops that
is scored is said). A loop through a link that cannot be scored (a decision with several inputs whose
response the model does not write, an equation with a delay inside it, an unsigned link) is said to be not
scored, with why."""

from __future__ import annotations

from ..spec import causal
from ..spec import equation as eq
from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

TIE = 1e-6               # relative scores closer than this are a tie: no loop is named


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


def _stocks(lp: causal.CausalLoop) -> list[str]:
    return [x for x in lp.parts if x.startswith("stock.")]


def dominance(spec: Spec, data: ob.Data, run: sim.Run | None = None, pl: sim.Plan | None = None) -> dict:
    """Each loop's score, and per stock each scored loop's relative score at each bucket (None where nothing
    along it changed), which loop dominates the stock then (None when tied, or not named because a loop through
    it is not scored), its share of the window, and for each loop not scored, why. ``run`` is not used: the
    replay is run again here with every part along a scored loop traced at each step."""
    pl = pl or sim.plan(spec)
    loops = causal.loops(spec)
    how, _ = scorer(spec, pl)
    n = data.grid.n
    scored, why = [], {}
    for lp in loops:
        bad = next((how[(x.source, x.target)][4:] for x in lp.links if how[(x.source, x.target)].startswith("why:")), None)
        if bad:
            why[lp.name] = bad
        else:
            scored.append(lp)
    trace: set[str] = set()
    for lp in scored:
        trace |= set(lp.parts)
        for x in lp.links:
            if how[(x.source, x.target)] == "equation":
                trace |= set(eq.refs(pl.eqs[x.target].tree))
            if how[(x.source, x.target)] == "material":
                trace |= {f"flow.{f.name}" for f in spec.flows_of(x.target[6:])}
    steps = sim.replay(spec, data, pl, trace=trace).trace if scored else []
    assumed = {lp.name: [f"{x.source} → {x.target}" for x in lp.links
                         if how[(x.source, x.target)] == "single" and not _known(steps, x.target)] for lp in scored}
    flows_of = {s: [(f"flow.{f.name}", f.target == s[6:]) for f in spec.flows_of(s[6:])] for lp in scored for s in _stocks(lp)}

    def net(vals: dict, stock: str) -> float | None:
        tot = 0.0
        for f, into in flows_of[stock]:
            v = vals.get(f)
            if v is None:
                return None
            tot += v if into else -v
        return tot

    def partial(x: causal.Link, a: dict, b: dict) -> float | None:
        c = pl.eqs[x.target]
        refs = eq.refs(c.tree)
        before = {r: a.get(r) for r in refs}
        after_all = {r: b.get(r) for r in refs}
        if any(v is None for v in (*before.values(), *after_all.values())):
            return None
        now = dict(before)
        now[x.source] = after_all[x.source]
        try:
            y0 = c.fn(before, pl.params, [], [], True)
            dz = c.fn(after_all, pl.params, [], [], True) - y0
            dxz = c.fn(now, pl.params, [], [], True) - y0
        except (ArithmeticError, ValueError):
            return None
        dx = now[x.source] - before[x.source]
        if not dz or not dx:
            return 0.0
        return abs(dxz / dz) * (1 if dxz / dx > 0 else -1 if dxz / dx < 0 else 0)

    def score(x: causal.Link, a: dict, b: dict) -> float | None:
        kind = how[(x.source, x.target)]
        if kind == "material":
            s0, s1, d0, d1 = net(a, x.target), net(b, x.target), a.get(x.source), b.get(x.source)
            if None in (s0, s1, d0, d1):
                return None
            return 0.0 if s1 == s0 else x.sign * abs((d1 - d0) / (s1 - s0))
        if kind == "equation":
            return partial(x, a, b)
        side = x.target if b.get(x.target) is not None else x.source      # assumed: it follows its one cause
        v0, v1 = a.get(side), b.get(side)
        if v0 is None or v1 is None:
            return None
        return 0.0 if v1 == v0 else float(x.sign)

    raw: dict[str, list[float | None]] = {lp.name: [] for lp in scored}
    at: list[int] = []
    for (_, a), (i1, b) in zip(steps, steps[1:], strict=False):
        at.append(i1)
        for lp in scored:
            s = 1.0
            for x in lp.links:
                v = score(x, a, b)
                if v is None:
                    s = None
                    break
                s *= v
            raw[lp.name].append(s)
    through: dict[str, list[str]] = {}
    for lp in loops:
        for s in _stocks(lp):
            through.setdefault(s, []).append(lp.name)
    stocks = {}
    names = {lp.name for lp in scored}
    for s, all_ in sorted(through.items()):
        mine = [k for k in all_ if k in names]
        if not mine:
            continue
        sums = {k: [0.0] * n for k in mine}
        counts = [0] * n
        for j, i in enumerate(at):
            tot = sum(abs(raw[k][j]) for k in mine if raw[k][j] is not None)
            if not tot:
                continue
            counts[i] += 1
            for k in mine:
                if raw[k][j] is not None:
                    sums[k][i] += raw[k][j] / tot
        rel = {k: [sums[k][i] / counts[i] if counts[i] else None for i in range(n)] for k in mine}
        named = len(mine) == len(all_)
        top: list[str | None] = [None] * n
        ties = 0
        for i in range(n):
            vals = sorted(((abs(rel[k][i]), k) for k in mine if rel[k][i] is not None), reverse=True)
            if not vals or not vals[0][0]:
                continue
            if len(vals) > 1 and vals[0][0] - vals[1][0] <= TIE:
                ties += 1
                top[i] = "="
            elif named:
                top[i] = vals[0][1]
        moving = sum(1 for c in counts if c)
        share = {k: (sum(1 for t in top if t == k) / moving if moving and named else None) for k in mine}
        stocks[s] = {"loops": all_, "scored": mine, "relative": rel, "dominant": [t if t != "=" else None for t in top],
                     "tied": [t == "=" for t in top], "ties": ties, "share": share, "named": named, "steps": moving}
    first = {lp.name: next((s for s in _stocks(lp) if s in stocks), None) for lp in scored}
    return {"times": data.grid.times(), "stocks": stocks, "first": first, "assumed": assumed,
            "relative": {k: stocks[s]["relative"][k] if s else [None] * n for k, s in first.items()},
            "share": {k: stocks[s]["share"][k] if s else None for k, s in first.items()},
            "not_scored": why, "polarity": {lp.name: lp.polarity for lp in loops},
            "steps": max((x["steps"] for x in stocks.values()), default=0), "integration_steps": len(at)}


def _known(steps: list, ref: str) -> bool:
    """The run has a value for this part (it is integrated, worked out, or an input it was driven by)."""
    return any(v.get(ref) is not None for _, v in steps[:3])
