"""Stocks to aggregate, from loop dominance over a window (SPEC §12c; Simon and Ando, "Aggregation of variables in
dynamic systems", *Econometrica* 29, 1961; Iwasaki and Simon, "Causality and model abstraction", *Artificial
Intelligence* 67, 1994): a chain of stocks whose stages were each driven only by their own drain behaves as one
delay, so the chain is a **candidate** to aggregate into one. A candidate, not a finding: it holds for the window the
dominance was scored over, and only for the loops ``causal.loops`` finds.

A stock qualifies when it is in the system's own chain (its innermost system), has its own balancing loop (one
running through no other stock: its drain), every loop through it is scored, it is named, moved in the window and was
never tied while a loop through other stocks runs through it, and no loop through it and another stock dominated any
stock in any bucket. Anything unknown disqualifies: the dominance missing or of other loops, a loop not scored, the
loop count at its cap. A group is a linear material chain of two or more qualifying stocks in one system (a branch or a
cycle among them gives none)."""

from __future__ import annotations

import time

from ..spec import causal
from ..spec.ir import Spec

MOST = 300       # causal.loops' own cap: at it, loops may be missing, so nothing is said


def _stocks(lp: causal.CausalLoop) -> list[str]:
    return [x for x in lp.parts if x.startswith("stock.")]


def qualifying(spec: Spec, dom: dict | None) -> set[str]:
    """The stocks that qualify (rule 1 of the definition): an empty set whenever the dominance cannot be read."""
    loops = causal.loops(spec, most=MOST)
    if not dom or len(loops) >= MOST or set(dom.get("polarity") or {}) != {lp.name for lp in loops}:
        return set()
    drove = {d for x in dom["stocks"].values() for d in x["dominant"] if d}
    through: dict[str, list[causal.CausalLoop]] = {}
    for lp in loops:
        for s in set(_stocks(lp)):
            through.setdefault(s, []).append(lp)
    out = set()
    for name in spec.stocks:                 # its system is checked where the groups are made
        s, mine = f"stock.{name}", through.get(f"stock.{name}", [])
        x = dom["stocks"].get(s)
        wide = [lp for lp in mine if len(set(_stocks(lp))) > 1]
        if (x is None or not x["named"] or not x["steps"] > 0
                or any(lp.name in dom["not_scored"] or lp.name not in x["scored"] for lp in mine)
                or not any(lp.polarity == "B" for lp in mine if lp not in wide)
                or any(lp.name in drove for lp in wide) or (wide and any(x["tied"]))):
            continue
        out.add(s)
    return out


def candidates(spec: Spec, dom: dict | None) -> dict[str, list[dict]] | None:
    """Per system, its groups of stocks to aggregate (``{stocks, said}``, in material order); None for a model with
    no systems. ``dom`` is ``dominance.dominance(spec, data)``; None (it could not be worked out) gives no groups."""
    if not spec.systems:
        return None
    ok = qualifying(spec, dom)
    times = (dom or {}).get("times") or []
    if len(times) < 2:
        ok = set()
    else:
        w = times[1] - times[0]
        since, until = (time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) for t in (times[0] - w / 2, times[-1] + w / 2))
    out: dict[str, list[dict]] = {}
    for system in sorted(spec.systems):
        mine = {s for s in ok if spec.stocks[s[6:]].system == system}
        nxt: dict[str, set[str]] = {s: set() for s in mine}
        prv: dict[str, set[str]] = {s: set() for s in mine}
        for f in spec.flows.values():
            a, b = f"stock.{f.source}", f"stock.{f.target}"
            if a in mine and b in mine and a != b:
                nxt[a].add(b)
                prv[b].add(a)
        groups, seen = [], set()
        for s in sorted(mine):
            if s in seen:
                continue
            part, todo = set(), [s]          # its component, joined by flows either way
            while todo:
                y = todo.pop()
                if y not in part:
                    part.add(y)
                    todo += [*nxt[y], *prv[y]]
            seen |= part
            heads = [y for y in part if not prv[y]]
            if len(part) < 2 or len(heads) != 1 or any(len(nxt[y]) > 1 or len(prv[y]) > 1 for y in part):
                continue                     # one stock, a branch or a cycle: not a chain
            chain = [heads[0]]
            while nxt[chain[-1]]:
                chain.append(next(iter(nxt[chain[-1]])))
            groups.append({"stocks": chain, "said": f"over the window ({since} to {until}) no feedback loop beyond each "
                                                    f"stock's own drove {', '.join(chain)}: a candidate to aggregate into one delay"})
        out[system] = groups
    return out
