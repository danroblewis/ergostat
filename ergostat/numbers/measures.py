"""The model's own quality, ergostat's built-in measures (SPEC §12e), each a reference ``ergostat.model.NAME``
read by a sensor (``sensor: {builtin: ergostat.model.fit}``) on a stock or an auxiliary, by ergostat itself
(``ergostat measure ergostat.model.fit``, in a process of its own, so a slow fit never holds up the engine). Each
is a measurement of the model against the record, like any sensor's, so a goal can hold it and a block act on it:

- **ergostat.model.fit**: the scaled error of the replay on the reference window, the Fit page's total (Oliva 2003: each
  stock's mean squared error over its own mean square, averaged); none while there is too little record;
- **ergostat.model.unexplained**: the share of each stock's change over the last hour that its flows do not explain (the
  residuals, SPEC §12b), |unexplained| / (|explained| + |unexplained|), averaged over the stocks that moved;
- **ergostat.model.unidentified-loops**: the goals whose loop closes and whose process (u to y) the model does not hold,
  declared or identified (SPEC §8, §12d);
- **ergostat.model.open-findings**: what ``ergostat check`` finds, errors aside (structure, signs, extreme conditions, control).

and how far blocks' claims hold (SPEC §12g, ``claims/trust.py``): ``ergostat.trust.contradicted`` and its counts, each
for every block or, with ``@WHO``, one block, rung or model; how the owner's messages reach the work (SPEC §12h,
``messages/measures.py``): ``ergostat.messages.unrouted``, ``.awaiting``, ``.missed`` and the rest; and how the work
each projection recipe started turned out (SPEC §12j, ``recipes/uses.py``): ``ergostat.context.RECIPE.outcome``,
``.cost`` and counts; and what the runs cost (SPEC §9.1, ``costs/record.py``): ``ergostat.cost.usd``, ``.tokens``,
``.cpu``, ``.memory``, ``.runs``, over the last day or hour, for every block or one.
"""

from __future__ import annotations

import time

from ..spec.ir import (
    ACTIONS,
    ACTIONS_MEASURES,
    CONTEXT_MEASURE,
    CONTEXT_MEASURES,
    COST,
    COST_MEASURES,
    INBOX_MEASURES,
    INTENT,
    INTENT_MEASURES,
    LEASE_MEASURES,
    LEASES,
    MESSAGE_MEASURES,
    MODEL_MEASURES,
    TRUST,
    TRUST_MEASURES,
    WORKSPACES,
    WORKSPACES_MEASURES,
)


class MeasureError(Exception):
    pass


def fit(p) -> float | None:
    from . import fit as ft
    _, run, got = ft.compute(p, {"at": time.time()})
    t = got.get("total")
    return t.get("nmse") if t and run.valid else None


def fit_why(p) -> tuple[float | None, str | None]:
    """The model's fit (``ergostat.model.fit``) and, when it cannot be worked out, why, in words that say what would
    make it measurable: stocks read by a sensor, flows that move them (an equation, or a sensor), and record."""
    from . import fit as ft
    spec = p.model.spec
    from ..spec.ir import template_made
    read = [n for n, st in spec.stocks.items() if st.sensors and not template_made(st)]
    if not read:
        return None, "no stock of the model's own is read by a sensor, so there is nothing to replay the model against"
    moved = [n for n in read if any(f.equation is not None or f.sensors or f.rate is not None for f in spec.flows_of(n))]
    if not moved:
        return None, (f"no flow of the stocks read ({', '.join(read[:4])}) has an equation or a sensor, so the replay "
                      f"cannot move them: an equation on each flow makes the fit measurable")
    try:
        _, run, got = ft.compute(p, {"at": time.time()})
    except Exception as e:                          # a replay that fails says why
        return None, f"the replay failed: {type(e).__name__}: {e}"
    t = got.get("total")
    if t and run.valid and t.get("nmse") is not None:
        return t["nmse"], None
    if not run.valid:
        return None, "the replay is not valid: " + "; ".join(run.invalid[:2])
    return None, (t or {}).get("says") or (t or {}).get("too_little") or "too little record yet to replay the model against"


def unexplained(p) -> float | None:
    from .. import state
    res = state.snapshot(p, state.WINDOW, None).get("residuals") or {}
    shares = []
    for r in res.values():
        u, e = abs(r.get("unexplained") or 0.0), abs(r.get("explained") or 0.0)
        if u + e > 1e-12:
            shares.append(u / (u + e))
    return sum(shares) / len(shares) if shares else 0.0


def loops_unidentified(p) -> float:
    spec = p.model.spec
    n = 0
    for g in spec.goals.values():
        try:
            closes = spec.loop(g.name).closes
        except Exception:
            closes = False
        if closes and not g.process:
            n += 1
    return float(n)


def findings(p) -> float:
    from ..spec import read
    _, problems = read(p.model.path)
    return float(sum(1 for x in problems if x.level not in ("error", "note")))   # a craft note is not a finding


def _meta():
    from . import meta
    return meta.READERS


READERS = {"ergostat.model.fit": fit, "ergostat.model.unexplained": unexplained,
           "ergostat.model.unidentified-loops": loops_unidentified, "ergostat.model.open-findings": findings,
           **{n: (lambda p, n=n: _meta()[n](p)) for n in ("ergostat.model.accepted-per-day", "ergostat.model.regressed",
                                                          "ergostat.model.verified-share", "ergostat.model.fit-gained",
                                                          "ergostat.model.cost-per-accepted")}}


def measure(p, name: str) -> float | None:
    if name.startswith(("trust.", "messages.", "intent.", "leases.", "actions.", "workspaces.", "inbox.", "interventions.",
                        "cost.")):                 # by hand: trust.contradicted@developer
        name = "ergostat." + name
    if not name.startswith("ergostat."):           # by hand, the short name will do: fit, open-findings
        name = "ergostat.model." + name.removeprefix("model.")
    if TRUST.match(name):                          # how far blocks' claims hold (SPEC §12g)
        from ..claims import trust
        return trust.measure(p, name)
    if COST.match(name):                           # what the runs cost: dollars, tokens, CPU, memory (SPEC §9.1)
        from ..costs import record as cr
        return cr.measure(p, name)
    if name in MESSAGE_MEASURES:                   # how the owner's messages reach the work (SPEC §12h)
        from ..messages import measures as mm
        return mm.measure(p, name)
    if CONTEXT_MEASURE.match(name):                # how the work each recipe started turned out (SPEC §12j)
        spec = getattr(p.model, "spec", None)
        if spec is None:
            raise MeasureError("the model is an ergostat.toml: its measures are read from ergostat.yaml")
        from ..recipes import uses
        return uses.measure(p, spec, name)
    if LEASES.match(name):                         # the leases on items (SPEC §9.5)
        spec = getattr(p.model, "spec", None)
        if spec is None:
            raise MeasureError("the model is an ergostat.toml: its measures are read from ergostat.yaml")
        from ..leases import measures as lm
        return lm.measure(p, spec, name)
    if INTENT.match(name):                         # how far finished work holds to what the owner meant (SPEC §12i)
        from ..intent import measures as im
        return im.measure(p, name)
    if ACTIONS.match(name):                        # the gated actions, by how their gates took them (SPEC §12k)
        from ..actions import record as ar
        return ar.measure(p, name)
    if name in INBOX_MEASURES:                     # what waits on a person (SPEC §12o)
        from ..inbox import entries, stats
        spec = getattr(p.model, "spec", None)
        if name.startswith("ergostat.interventions."):
            from ..inbox.interventions import measures as im
            return float(im(p, spec)[name.rsplit(".", 1)[1]]) if spec is not None else 0.0
        es = entries.entries(p, spec) if spec is not None else []
        if name.endswith("asked"):
            return float(len(stats.asked_today(p, spec))) if spec is not None else 0.0
        return float(len(es)) if name.endswith("waiting") else max((e["age"] for e in es), default=0.0) / 3600.0
    if m := WORKSPACES.match(name):                # the workspace pools, now (SPEC §12k)
        spec = getattr(p.model, "spec", None)
        if spec is None:
            raise MeasureError("the model is an ergostat.toml: its measures are read from ergostat.yaml")
        from ..workspaces import pool as wp
        if m.group(2) and m.group(2) not in spec.workspaces:
            raise MeasureError(f"no workspace pool {m.group(2)!r}")
        return float(wp.counts(p, spec, m.group(2))[m.group(1)])
    if name not in MODEL_MEASURES:
        known = [*MODEL_MEASURES, *TRUST_MEASURES, *MESSAGE_MEASURES, *CONTEXT_MEASURES, *INTENT_MEASURES, *LEASE_MEASURES,
                 *ACTIONS_MEASURES, *WORKSPACES_MEASURES, *COST_MEASURES,
                 *INBOX_MEASURES]
        raise MeasureError(f"no measure {name!r}: {', '.join(known)}")
    if getattr(p.model, "spec", None) is None:
        raise MeasureError("the model is an ergostat.toml: its measures are read from ergostat.yaml")
    return READERS[name](p)


def all_of(p) -> dict[str, float | None]:
    out = {}
    for n in [*MODEL_MEASURES, *TRUST_MEASURES, *MESSAGE_MEASURES, *INTENT_MEASURES, *LEASE_MEASURES, *ACTIONS_MEASURES,
              *WORKSPACES_MEASURES, *COST_MEASURES, *INBOX_MEASURES]:
        try:
            out[n] = measure(p, n)
        except Exception as e:                        # one measure that cannot be read leaves the others
            out[n] = None
            out[f"{n}_error"] = f"{type(e).__name__}: {e}"
    return out
