"""Two changes proposed to the built-in judge (``numbers/judge.py``), found by its error rates (SPEC §12f), tried by
putting this ``compare`` in place of the judge's while the benchmark runs (``variant``):

- **like for like**: the judge's ``compare`` takes each model's fit total, and the total leaves out a stock whose
  replay is slower than the window is long; a change that slows a stock enough takes it out of the total and looks
  better in every window. Here the two models are compared over the same stocks, each stock's scaled error counted
  whatever its time constant;
- **warm windows**: each window is replayed from its own first reading, every delay in equilibrium, so a correct
  delay often scores worse in a short window than none at all. Here each window is scored on a replay started
  ``WARM_HOURS`` before it."""

from __future__ import annotations

import contextlib

from ..numbers import fit as ft
from ..numbers import judge as jd
from ..numbers import observe as ob
from ..numbers import simulate as sim
from ..spec.ir import Spec

WARM_HOURS = 6.0


def per_stock(spec: Spec, data: ob.Data, run, first: int = 0) -> dict[str, float]:
    """Each stock's scaled error (mean squared error over the record's mean square) from bucket ``first`` on,
    whether or not the fit's total would count it."""
    out = {}
    for ref in run.how:
        if not ref.startswith("stock."):
            continue
        got = [(m, a) for i, m, a in ft.pairs(spec, data, run, ref) or [] if i >= first]
        if len(got) < 5:
            continue
        mse = sum((m - a) ** 2 for m, a in got) / len(got)
        scale = sum(a * a for _, a in got) / len(got)
        out[ref] = mse / (scale or 1.0)
    return out


def scored(p, spec: Spec, since: float, until: float, warm: bool) -> dict[str, float] | None:
    start = since - WARM_HOURS * 3600.0 if warm else since
    width = max(ob.MIN_BUCKET, (until - since) / 30.0) if warm else (until - since) / jd._grid(since, until).n
    grid = ob.Grid(start, until, max(2, int(round((until - start) / width))))
    data = ob.measured(p, grid, spec)
    run = sim.replay(spec, data)
    if not run.valid:
        return None
    return per_stock(spec, data, run, int((since - start) // grid.width))


def compare(p, spec: Spec, after: Spec, since: float, until: float, like: bool = True, warm: bool = True) -> dict:
    if not like:
        if not warm:
            return _ORIGINAL(p, spec, after, since, until)
    sb, sa = scored(p, spec, since, until, warm), scored(p, after, since, until, warm)
    b = a = None
    if sb and sa:
        common = sorted(set(sb) & set(sa)) if like else None
        if like and common:
            b, a = sum(sb[r] for r in common) / len(common), sum(sa[r] for r in common) / len(common)
        elif not like:
            b, a = sum(sb.values()) / len(sb), sum(sa.values()) / len(sa)
    change = (b - a) / b if b and a is not None else (0.0 if b == 0 and a == 0 else None)
    return {"since": since, "until": until, "before": b, "after": a, "change": change}


_ORIGINAL = jd.compare


@contextlib.contextmanager
def variant(like: bool = False, warm: bool = False):
    """The judge with these changes, while inside; as built when both are off."""
    if not (like or warm):
        yield "as built"
        return
    jd.compare = lambda p, spec, after, since, until: compare(p, spec, after, since, until, like, warm)
    try:
        yield ", ".join(n for n, on in (("like for like", like), ("warm windows", warm)) if on)
    finally:
        jd.compare = _ORIGINAL
