"""The page's view of the model's numbers: the replay and projection drawn on the causes strip, an
equation and its parameters in a valve's or an auxiliary's panel, the Fit page, and the one thing
the page may change: a proposal the owner accepts or dismisses (``POST``)."""

from __future__ import annotations

import threading
import time

from .. import series
from ..numbers import estimate as es
from ..numbers import fit as ft
from ..numbers import observe as ob
from ..numbers import proposals as pr
from ..numbers import simulate as sim
from ..numbers import version as ver
from ..spec import equation as eq

ESTIMATING = threading.Lock()     # one estimate at a time: each is a few hundred replays
HORIZON = 0.25           # a projection looks ahead at most a quarter of the window ...
LEAST = 0.05             # ... at least a twentieth of it ...
DOMINANT = 3.0           # ... and, between, three of the slowest time constant the replay met


def spec_of(p):
    return getattr(p.model, "spec", None)


def horizon_of(run: sim.Run, window: float) -> float:
    """How far a projection looks: a few of the model's slowest time constants, within a twentieth and
    a quarter of the window."""
    slow = max((v for r, v in run.time_constants.items() if r.startswith("stock.")), default=None)
    if not slow:
        return window * HORIZON
    return min(window * HORIZON, max(window * LEAST, DOMINANT * slow * 3600.0))


def model_run(live, p, snap: dict, n: int = series.POINTS, inputs: str = "hold") -> dict | None:
    """The replay and the projection on the page's grid, for the charts: shared by the requests of a
    few seconds (the strip and the panels ask together). The fit is not of this grid (``reference``)."""
    spec = spec_of(p)
    if spec is None:
        return None
    key = ("numbers", snap["window"], snap["at"] if not snap.get("live", True) else round(snap["at"] / 5), live.mtime, n, inputs)
    got = live.cached(key)
    if got is not None:
        return got
    since, until = series.span(p, snap)
    data = ob.measured(p, ob.Grid(since, until, n))
    pl = sim.plan(spec)
    run = sim.replay(spec, data, pl)
    horizon = horizon_of(run, until - since)
    proj = sim.project(spec, data, run, horizon, pl, points=max(2, round(n * horizon / max(until - since, 1.0))), inputs=inputs)
    got = {"data": data, "run": run, "projection": proj, "horizon": horizon}
    live.keep(key, got)
    return got


def reference(live, p, snap: dict) -> dict | None:
    """The fit on the reference window (the last day of record), whatever window the page shows: the
    Fit page's, the panels', and what the history records."""
    spec = spec_of(p)
    if spec is None:
        return None
    key = ("fit", snap["at"] if not snap.get("live", True) else round(snap["at"] / 15), live.mtime)
    got = live.cached(key)
    if got is not None:
        return got
    data, run, fit = ft.compute(p, {"at": snap["at"]})
    got = {"data": data, "run": run, "fit": fit}
    live.keep(key, got)
    return got


def _round(vals):
    return [None if v is None else round(v, 6) for v in vals]


def add_to_series(live, p, snap: dict, out: dict, inputs: str = "hold") -> dict:
    """Each part's replay (what the model says it was) and projection (what it says comes next),
    where the model works it out: an integrated stock, a flow or auxiliary with an equation."""
    mr = model_run(live, p, snap, out["points"], "trend" if inputs == "trend" else "hold")
    if mr is None:
        return out
    run, proj = mr["run"], mr["projection"]
    for s in out["series"]:
        ref = s["ref"]
        if ref in run.how:
            s["replay"] = _round(run.values[ref])
            s["projection"] = _round(proj.values.get(ref) or [])
            s["modelled"] = run.how[ref]
    if any("replay" in s for s in out["series"]):
        out["projection_times"] = [round(t, 3) for t in proj.times]
        out["horizon"] = mr["horizon"]
        out["inputs"] = "; ".join(mr["projection"].notes)
        out["replay_notes"] = run.notes + run.invalid
    return out


def parameter_rows(p, spec, names: list[str]) -> list[dict]:
    """Each parameter an equation names: its value and where it comes from (declared, estimated or
    unknown), and its estimate beside it when there is one."""
    est = es.load(p, spec)
    rows = []
    for nm in names:
        x = spec.parameters.get(nm)
        if x is None:
            continue
        e = est.get(nm)
        rows.append({"name": nm, "value": x.value, "unit": x.unit, "provenance": x.provenance, "estimate": x.estimate,
                     "duration": x.duration,
                     "table": x.table, "description": x.description,
                     "where": str(x.defined) if x.defined else None,
                     "estimated": None if not e or e.get("value") is None else
                     {**{k: e.get(k) for k in ("value", "n", "when", "window", "before", "after", "held_before", "held_after",
                                                "fitted_to", "at_bound", "corr", "slowest")},
                      "se": es.said_se(e, e["value"])},
                     "estimate_note": (e.get("why") if e and e.get("value") is None else e.get("refused") if e else None)})
    return rows


def part_numbers(live, p, snap: dict, kind: str, name: str) -> dict:
    """What a valve's (flow's) or an auxiliary's panel shows of its numbers."""
    spec = spec_of(p)
    if spec is None:
        return {}
    x = spec.measured(kind).get(name)
    if x is None:
        return {}
    ref = f"{kind}.{name}"
    out: dict = {"proposals": [y for y in pr.pending(p, spec) if ref in y.get("parts", [])]}
    e = getattr(x, "equation", None)
    if e is None:
        return out
    from ..spec.equation_checks import units
    got, want, problems = units(spec, kind, name)
    rf = reference(live, p, snap)
    run = rf["run"] if rf else None
    fit = rf["fit"] if rf else {}
    out.update(equation_text=e.text, equation_tree=eq.tree_json(e.tree), parameters=parameter_rows(p, spec, e.parameters),
               equation_unit=eq.unit_text(got) if got is not None else None, unit_problems=problems,
               equation_ok=bool(got is None or want is None or got == want),
               replayed=run is not None and ref in run.how,
               left_out=next((n for n in run.notes if n.startswith(ref + ":")), None) if run else None,
               fit_span=fit.get("span"),
               partial=ft._slim((fit.get("partial") or {}).get(ref)), replay=ft._slim((fit.get("equations") or {}).get(ref)),
               judged_by_stock=(fit.get("judged_by_stock") or {}).get(ref),
               stock_fit=ft._slim((fit.get("stocks") or {}).get((fit.get("judged_by_stock") or {}).get(ref) or "")),
               invalid=fit.get("invalid") or [])
    return out


def fit_page(live, p, snap: dict) -> dict | None:
    spec = spec_of(p)
    if spec is None:
        return None
    rf = reference(live, p, snap)
    fit = rf["fit"]
    if snap.get("live", True):
        ft.record(p, fit)
    units = {f"stock.{n}": s.unit for n, s in spec.stocks.items()} | {f"flow.{n}": f.unit for n, f in spec.flows.items()} | \
            {f"auxiliary.{n}": a.unit for n, a in spec.auxiliaries.items()}

    def rows(part):
        return [{"ref": r, "name": r.split(".", 1)[1], "unit": units.get(r, ""), **(ft._slim(s) or {"n": None})}
                for r, s in sorted(fit[part].items())]
    est = es.load(p, spec)
    return {"version": ver.version(spec), "structure": ver.structure(spec), "since": rf["data"].grid.since,
            "until": rf["data"].grid.until, "total": ft._slim(fit["total"]), "stocks": rows("stocks"),
            "accounting": rows("accounting"), "equations": rows("equations"), "partial": rows("partial"),
            "judged_by_stock": fit["judged_by_stock"], "invalid": fit["invalid"],
            "notes": rf["run"].notes, "words": ft.WORDS, "min_points": ft.MIN_POINTS,
            "history": ft.versions(p), "accepted": pr.accepted(p), "proposals": pr.pending(p, spec),
            "estimated_at": max((e.get("when") or 0 for e in est.values()), default=None) or None,
            "to_estimate": sorted(n for n, x in spec.parameters.items() if x.estimate and not x.table),
            "not_proposed": {n: e.get("refused") or e.get("why") for n, e in est.items()
                             if n in spec.parameters and (e.get("refused") or e.get("why"))},
            "residuals": snap.get("residuals", {})}


def post(live, path: str, window: float) -> tuple[int, dict]:
    """``POST /api/estimate`` (estimate, and make the proposals), ``/api/proposals/ID/accept`` and
    ``/api/proposals/ID/dismiss``: the page's only writes, each the owner's own act."""
    p = live.get()
    if spec_of(p) is None:
        return 400, {"error": "the model is an ergostat.toml: equations are written in ergostat.yaml"}
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=None)
    parts = path.strip("/").split("/")
    snap = {"at": time.time(), "window": window, "starts": oldest}
    try:
        if parts == ["estimate"]:
            if not ESTIMATING.acquire(blocking=False):
                return 409, {"error": "already estimating: its proposals come when it ends"}
            try:
                return 200, {"proposals": pr.make(p, snap)}
            finally:
                ESTIMATING.release()
        if len(parts) == 3 and parts[0] == "proposals" and parts[2] in ("accept", "dismiss"):
            if parts[2] == "dismiss":
                return 200, pr.dismiss(p, parts[1])
            got = pr.accept(p, parts[1], snap, by="owner")
            live.reloaded()
            return 200, got
    except pr.ProposalError as e:
        return 409, {"error": str(e)}
    return 404, {"error": "not found"}
