"""A missing delay on a stock's inflow, found from the stock's one-step residuals (``residuals.py``; the narrow core of SD
Lab's hidden-transit discovery and of the "autocorrelated → hidden stock or delay" row of residual diagnostics).

A measured stock whose residual is coloured is looked at for the inflow whose lag explains it (the regressor
u(i−k) − u(i)); that inflow is then tried late by τ = ½, 1 and 2 times k buckets, in two forms: a third-order
material delay (``DELAY3``) and a first-order one drawn as a stock in transit, never read, that starts at its
equilibrium. Each edit is compiled in memory and the stock's residual worked out again on the model it leaves (the
residual run of that model, its transit stock integrated from the ``initial:`` the edit writes). The best is
offered when its residual's sum of squares falls by a fifth and its whiteness statistic falls; every other is
listed with its numbers, and one that cannot be compiled, replayed or worked out is not offered (it fails closed).

It finds one kind of missing structure: a delay between an inflow and the measured stock it fills. Not a missing
outflow, a missing cause, a delay on an outflow, or a part replaced by another form. One look runs at most
``MOST_REPLAYS`` residual runs; a stock's six are charged before it is started."""

from __future__ import annotations

import math

from . import observe as ob
from . import residuals as rs
from . import structural as stc
from . import trial as tr
from . import yamledit as ye

MOST_REPLAYS = 30          # residual runs in one look, the model's own counted
TAUS = (0.5, 1.0, 2.0)     # τ tried, times the lag's k buckets
SHRINK = 0.8               # offered when the residual's sum of squares is at most this share of what it was
FORMS = ("residual-delay", "residual-hidden-stock")
PER_STOCK = len(FORMS) * len(TAUS)
METHOD = ("the stock's one-step residuals (its change from bucket to bucket less what the model's flows moved in it), "
          "tested for whiteness by a Box–Pierce portmanteau over lags 2 to 10 with Bartlett's MA(1) covariance for "
          f"lag 1 (χ²(9), coloured past {rs.CHI2_9_99}); the inflow and lag whose regressor u(i−k) − u(i) the residual "
          f"follows; τ tried at {', '.join(map(str, TAUS))} times the lag; each form's edit compiled and its residual "
          f"worked out again by the residual run of the model it leaves (stocks never read integrated from their "
          f"initial:, every other taken as read)")


def _no(c, x: str, why: str, code: str = "residual-delay") -> None:
    c.not_made.append({"title": f"A delay on an inflow of {x}", "code": code, "why": why})


def _dismissed(p) -> set[str]:
    from . import proposals as pr
    return {x.get("target") for x in pr.stored(p).values()
            if str(x.get("code") or "").startswith("residual-") and x["status"] == "dismissed"}


def find(c) -> None:
    spec, data = c.spec, c.data
    if data is None:
        return
    used = 1
    try:
        before = rs.residual_run(spec, data)
    except Exception as e:                       # any failure of the run fails closed
        _no(c, "any stock", f"the model's residual run failed ({e})")
        return
    if before.invalid:
        _no(c, "any stock", f"the model's residual run is not valid ({'; '.join(before.invalid)[:200]})")
        return
    no_again = _dismissed(c.p)
    for x, st in spec.stocks.items():
        if not st.sensors or not spec.flows_of(x):
            continue
        why = rs.examinable(spec, data, x)
        if why:
            _no(c, x, why)
            continue
        e = rs.residuals(spec, data, before, x)
        n = sum(v is not None for v in e)
        if n < rs.MIN_POINTS:
            unknown = [f.name for f in spec.flows_of(x)
                       if sum(v is None for v in rs.moved(spec, data, before, f.name)) > len(e) - rs.MIN_POINTS]
            said = f": {', '.join(unknown)} neither measured nor worked out in most buckets" if unknown else ""
            _no(c, x, f"{n} residuals, under {rs.MIN_POINTS}{said}: its residual cannot be worked out")
            continue
        q, coloured = rs.whiteness(e)
        if not coloured:
            continue
        cands = rs.inflows(spec, x)
        if not cands:
            _no(c, x, f"{x}'s residual is coloured (q {q:.1f} against {rs.CHI2_9_99}) but its inflows are already delayed, "
                      f"drawn from a stock ergostat cannot read, or measured by {x} itself")
            continue
        if f"stock.{x}" in no_again:
            _no(c, x, f"{x}'s residual is coloured (q {q:.1f}), but a delay on its inflow was dismissed: not proposed again")
            continue
        best = None
        for f in cands:
            u = rs.moved(spec, data, before, f.name)
            got = rs.lag_of(e, u, min(rs.MOST_LAG, n // 4))
            if got and (best is None or got[1] > best[2]):
                best = (f, *got, u)
        if best is None:
            _no(c, x, f"{x}'s residual is coloured (q {q:.1f}), but no inflow's lag explains it")
            continue
        if used + PER_STOCK > MOST_REPLAYS:
            _no(c, x, f"not examined: the finder's budget of {MOST_REPLAYS} replays was used")
            continue
        used += PER_STOCK
        _tried(c, x, *best, e)


def _tried(c, x: str, f, k: int, corr: float, u: list, e: list) -> None:
    data, w = c.data, c.data.grid.width / 3600.0
    names = {"delay": stc._free(f"{f.name}-delay", c.taken), "arrives": stc._free(f"{x}-arrives", c.taken),
             "transit": stc._free(f"{f.name}-in-transit", c.taken)}
    warm = math.ceil(3 * max(TAUS) * k)
    first = [v for v in u[:max(k, 1)] if v is not None]
    rate = sum(first) / len(first) / w if first else None
    tried, offered = [], []
    for form in FORMS:
        for m in TAUS:
            tau = m * k * w
            said = f"{'DELAY3' if form == 'residual-delay' else 'a stock in transit'}, τ {ye.duration(tau)}"
            try:
                if form == FORMS[1] and rate is None:
                    raise ye.EditError(f"{f.name}'s first rate is not known, so the stock in transit has no initial:")
                edits = _edits(c, form, x, f, tau, names, (rate or 0.0) * tau)
                after = tr.spec_after(c.p, edits)
            except (ye.EditError, tr.TrialError) as err:
                tried.append((said, None, f"its edit cannot be made ({err})"))
                continue
            try:
                d_a = ob.measured(c.p, data.grid, after)
                run = rs.residual_run(after, d_a)
            except Exception as err:             # a run that raises fails the candidate closed
                tried.append((said, None, f"its residual run failed ({err})"))
                continue
            if run.invalid:
                tried.append((said, None, f"its residual run is not valid ({'; '.join(run.invalid)[:200]})"))
                continue
            e_a = rs.residuals(after, d_a, run, x)
            at = [i for i in range(warm, len(e)) if e[i] is not None and e_a[i] is not None]
            if len(at) < rs.MIN_POINTS:
                tried.append((said, None, f"its residual at {x} can be worked out in {len(at)} buckets after the warm-up "
                                          f"of {warm}, under {rs.MIN_POINTS}"))
                continue
            sse_b, sse_a = sum(e[i] ** 2 for i in at), sum(e_a[i] ** 2 for i in at)
            on = set(at)
            q_b = rs.whiteness([e[i] if i in on else None for i in range(len(e))])[0]
            q_a = rs.whiteness([e_a[i] if i in on else None for i in range(len(e))])[0]
            nums = {"form": form, "tau": tau, "edits": edits, "sse": (sse_b, sse_a), "q": (q_b, q_a), "n": len(at)}
            if sse_a <= SHRINK * sse_b and q_a < q_b:
                offered.append(nums)
            tried.append((said, nums, None))
    best = min(offered, key=lambda z: z["sse"][1]) if offered else None
    for said, nums, why in tried:
        if nums is best and best is not None:
            continue
        if nums is not None:
            why = (f"SSE {ye.number(nums['sse'][0])} → {ye.number(nums['sse'][1])}, q {nums['q'][0]:.1f} → {nums['q'][1]:.1f}"
                   + (": a better candidate is offered" if nums in offered else
                      f": not offered (it needs SSE at most {SHRINK:.0%} of before and q lower)"))
        _no(c, x, f"{said} on {f.name}: {why}", code=nums["form"] if nums else "residual-delay")
    if best is None:
        return
    (sb, sa), (qb, qa), tau = best["sse"], best["q"], best["tau"]
    hidden = best["form"] == FORMS[1]
    title = (f"{f.name} reaches {x} through a stock in transit, {names['transit']} (τ {ye.duration(tau)})" if hidden else
             f"{f.name} reaches {x} through a third-order delay (DELAY3, τ {ye.duration(tau)})")
    parts = [f"stock.{x}", f"flow.{f.name}"]
    c.add("a missing delay on an inflow, as a stock in transit" if hidden else "a missing delay on an inflow, as DELAY3",
          best["form"], f"stock.{x}", title, parts,
          f"{x}'s residuals (its change from one bucket to the next, less what the model's flows moved in it) are coloured: "
          f"q {qb:.1f}, against {rs.CHI2_9_99:.2f} (χ²(9) at 0.99). They follow what {f.name} moved {k} bucket"
          f"{'s' if k > 1 else ''} before less what it moves now (correlation {corr:.2f}): what {f.name} moves reaches {x} "
          f"late. With it delayed by τ {ye.duration(tau)} the residuals' sum of squares goes {ye.number(sb)} → "
          f"{ye.number(sa)} over the same {best['n']} buckets, and q {qb:.1f} → {qa:.1f}.",
          METHOD, best["edits"], touched=[f"stock.{x}"],
          residual={"q": [qb, qa], "sse": [sb, sa], "k": k, "corr": corr, "tau": tau, "n": best["n"], "inflow": f"flow.{f.name}"})


def _edits(c, form: str, x: str, f, tau: float, names: dict, initial: float) -> list[ye.Edit]:
    spec = c.spec
    ye.own(f.where, f"flow {f.name}")
    path, at = stc._name_at(f, f.name)
    near = stc._section_file(spec, spec.stocks[x])
    pending = f"    inferred: {stc.PENDING}"
    edits = [ye.add_entries(near, "parameters", [[f"  {names['delay']}:", f"    value: {ye.number(tau)}", "    unit: h",
                                                   f"    description: how late what {f.name} moves reaches {x}",
                                                   "    estimate: true          # from the residuals; refitted as the record grows",
                                                   pending]])]
    if form == FORMS[0] and f.equation and not f.source:
        return edits + [ye.set_key(path, at, "equation", f"DELAY3({f.equation.text}, {names['delay']})")]
    if form == FORMS[0]:
        gone = ye.remove_key(path, at, "to")
        if gone is None:
            raise ye.EditError(f"{f.name}: no to: to take off")
        return edits + [gone, ye.add_entries(near, "flows", [[
            f"  {names['arrives']}:", f"    to: {x}", f"    description: what {f.name} moves, reaching {x} late",
            f"    driven-by: +flow.{f.name}", f"    equation: DELAY3(flow.{f.name}, {names['delay']})", pending]])]
    t, unit = names["transit"], spec.stocks[x].unit
    return edits + [
        ye.add_entries(near, "stocks", [[f"  {t}:"] + ([f"    unit: {unit}"] if unit else []) +
                                        [f"    initial: {ye.number(initial)}",
                                         f"    description: what {f.name} has moved that has not reached {x} yet (never read)",
                                         pending]]),
        ye.set_key(path, at, "to", t),
        ye.add_entries(near, "flows", [[f"  {names['arrives']}:", f"    from: {t}", f"    to: {x}",
                                        f"    description: what reaches {x} from {t}",
                                        f"    driven-by: +stock.{t}", f"    equation: stock.{t} / {names['delay']}", pending]])]
