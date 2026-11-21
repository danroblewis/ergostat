"""The page's view of the model's numbers: the replay and projection drawn on the causes strip, an
equation and its parameters in a valve's or an auxiliary's panel, the Model page, and the one thing
the page may change: a proposal the owner accepts or dismisses (``POST``)."""

from __future__ import annotations

import threading
import time

from .. import series
from ..numbers import aggregation as ag
from ..numbers import closedloop as cl
from ..numbers import dominance as dm
from ..numbers import estimate as es
from ..numbers import fit as ft
from ..numbers import observe as ob
from ..numbers import proposals as pr
from ..numbers import review as rv
from ..numbers import sensitivity as sens
from ..numbers import simulate as sim
from ..numbers import version as ver
from ..numbers.simulate import horizon_of  # noqa: F401  (the page's and the command line's horizon)
from ..spec import equation as eq
from ..webaccess import who

ESTIMATING = threading.Lock()     # one estimate at a time: each is a few hundred replays
RISK_BUDGET = 8.0        # seconds the page's closed-loop Monte Carlo may take; past it, it says how many runs it made
SAMPLED_KEYS = ("name", "how", "low", "high", "value", "sd", "unit", "duration")   # what the strip says of each sampled


def spec_of(p):
    return getattr(p.model, "spec", None)


def loops_of(spec, asked: str | None) -> str:
    """How the projection runs: ``closed`` (with the loops running, closedloop.py) or ``held`` (open loop). Closed by
    default where the model has controllers."""
    if asked in ("closed", "held"):
        return asked
    return "closed" if spec is not None and cl.has_controllers(spec) else "held"


def models_of(live, p, snap: dict) -> dict:
    """Each machine block's identified model, on the reference window whatever window the page shows (half a minute)."""
    key = ("models", snap["at"] if not snap.get("live", True) else round(snap["at"] / 30), live.mtime)
    got = live.cached(key)
    if got is None:
        got = cl.identify(p, spec_of(p), ob.measured(p, ob.reference(p, snap["at"])))
        live.keep(key, got)
    return got


def model_run(live, p, snap: dict, n: int = series.POINTS, inputs: str = "hold", whatif: dict | None = None,
              horizon: float | None = None, loops: str = "held", other: cl.WhatIf | None = None) -> dict | None:
    """The replay and the projection on the page's grid, for the charts: shared by the requests of a
    few seconds (the strip and the panels ask together). The fit is not of this grid (``reference``).
    ``whatif`` tries other values for some parameters (nothing is kept: a what-if); ``loops`` and ``other`` (the
    what-ifs only a closed loop tries): ``closedloop.projection``."""
    spec = spec_of(p)
    if spec is None:
        return None
    other = other or cl.WhatIf()
    key = ("numbers", snap["window"], snap["at"] if not snap.get("live", True) else round(snap["at"] / 5), live.mtime, n, inputs,
           tuple(sorted((whatif or {}).items())), horizon, loops, other.key())
    got = live.cached(key)
    if got is not None:
        return got
    since, until = series.span(p, snap)
    data = ob.measured(p, ob.Grid(since, until, n))
    pl = sim.plan(spec, whatif or None)
    run = sim.replay(spec, data, pl)
    horizon = horizon or horizon_of(run, until - since)
    points = max(2, round(n * horizon / max(until - since, 1.0)))
    got = {"data": data, "run": run, "horizon": horizon, "points": points, "loops": loops,
           **cl.projection(p, spec, data, run, horizon, pl, points, loops, inputs, other,
                           models_of(live, p, snap) if loops == "closed" else None)}
    live.keep(key, got)
    return got


RISKING: dict = {}        # the risks being worked out, by key: one at a time for each, in a thread of its own
RISKING_LOCK = threading.Lock()


def risk_of(live, p, snap: dict, mr: dict, inputs: str) -> dict | None:
    """The closed-loop projection's Monte Carlo (closedloop.risk), cached as the model run is (half a minute when live),
    worked out once however many ask, in a thread of its own so the page's other requests are not held behind it: None
    while it is being worked out."""
    spec = spec_of(p)
    key = ("risk", snap["window"], snap["at"] if not snap.get("live", True) else round(snap["at"] / 30), live.mtime,
           mr["data"].grid.n, inputs)
    got = live.cached(key)
    if got is not None:
        return got
    with RISKING_LOCK:
        if key not in RISKING:
            def work():
                try:
                    live.keep(key, cl.risk(spec, mr["data"], mr["run"], mr["horizon"], mr["points"], mr["models"],
                                           mr["start"], sens.estimates(p, spec), None, inputs, budget=RISK_BUDGET))
                finally:
                    with RISKING_LOCK:
                        RISKING.pop(key, None)
            RISKING[key] = threading.Thread(target=work, name="ergostat-risk", daemon=True)
            RISKING[key].start()
    return None


IMPACTS: dict = {}           # impact reports by key: (when kept, the report), each kept IMPACT_TTL seconds
IMPACTING: dict = {}         # ... being worked out, at most IMPACT_THREADS at once
IMPACT_TTL, IMPACT_THREADS = 300.0, 2


def impact(live, p, snap: dict, one) -> dict:
    """``GET /api/impact?block=NAME|item=ID|change=ID[&began=T&within=S&penalty=H]``: the impact report (SPEC §12n), worked
    out in a thread of its own; ``{"working": true, "at"}`` until then, the page asking again with that ``at``, so every
    request of one page is the same report; an error as ``{"error"}``."""
    from ..numbers import impact as im
    what = one("item") or one("change") or one("block")
    if not what:
        return {"error": "say which: block=NAME, item=ID or change=ID"}
    num = lambda k: float(one(k)) if one(k) else None   # noqa: E731
    try:
        began, within, penalty = num("began"), num("within"), num("penalty")
    except ValueError:
        return {"error": "began, within and penalty are numbers (epoch seconds, seconds, hours)"}
    at, now = snap["at"], time.monotonic()
    key = (str(p.dir), what, began, within, penalty, live.mtime, at)
    with RISKING_LOCK:
        for k in [k for k, (t, _) in IMPACTS.items() if now - t > IMPACT_TTL]:
            IMPACTS.pop(k)
        if key in IMPACTS:
            return IMPACTS[key][1]
        if key not in IMPACTING and len(IMPACTING) < IMPACT_THREADS:
            def work():
                r = {"error": "it could not be worked out"}
                try:
                    r = im.report(p, what, began, at=at, within=within, penalty=penalty, budget=RISK_BUDGET * 2)
                except Exception as e:                  # said on the page, never left working for ever
                    r = {"error": str(e)}
                finally:
                    with RISKING_LOCK:
                        IMPACTS[key] = (time.monotonic(), r)
                        IMPACTING.pop(key, None)
            IMPACTING[key] = threading.Thread(target=work, name="ergostat-impact", daemon=True)
            IMPACTING[key].start()
    return {"working": True, "at": at}


def fan_of(live, p, snap: dict, mr: dict, inputs: str) -> dict | None:
    """The projection's Monte Carlo fan over the uncertain parameters (sensitivity.py), cached as the
    model run is (the same moment, window, grid and inputs)."""
    spec = spec_of(p)
    key = ("fan", snap["window"], snap["at"] if not snap.get("live", True) else round(snap["at"] / 30), live.mtime,
           mr["data"].grid.n, inputs)
    got = live.cached(key)
    if got is not None:
        return got
    got = sens.fan(spec, mr["data"], mr["horizon"], mr["points"], inputs, sens.estimates(p, spec), run=mr["run"])
    live.keep(key, got)
    return got


def replay_fan_of(live, p, snap: dict, mr: dict) -> dict | None:
    """The replay's spread over the uncertain parameters across the window (sensitivity.replay_fan), cached as the
    model run is."""
    key = ("replay-fan", snap["window"], snap["at"] if not snap.get("live", True) else round(snap["at"] / 15), live.mtime,
           mr["data"].grid.n)
    got = live.cached(key)
    if got is None:
        got = sens.replay_fan(spec_of(p), mr["data"], sens.estimates(p, spec_of(p)))
        live.keep(key, got)
    return got


def reference(live, p, snap: dict) -> dict | None:
    """The fit on the reference window (the last day of record), whatever window the page shows: the
    Model page's, the panels', and what the history records."""
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


def parse_whatif(spec, raw: str | None) -> dict[str, float]:
    """``name:value,name:value``, each value a number in the parameter's unit or a duration (the parameters only:
    ``split_whatif`` keeps the rest)."""
    return split_whatif(spec, raw)[0]


def split_whatif(spec, raw: str | None) -> tuple[dict[str, float], cl.WhatIf]:
    """``name:value,...``: the parameters' values tried, and what only the closed-loop projection can try:
    ``flow.NAME`` (an input's rate per hour, or ``x2``), ``goal.NAME`` (a setpoint), ``block.NAME.pool``."""
    got = {}
    for part in (raw or "").split(","):
        if ":" in part:
            k, _, v = part.partition(":")
            got[k.strip()] = v.strip()
    try:
        params, other = cl.parse_whatif(spec, got)
    except cl.WhatIfError as e:
        raise pr.ProposalError(str(e)) from None
    return (pr.what_if(spec, params) if params else {}), other


def add_to_series(live, p, snap: dict, out: dict, inputs: str = "hold", whatif: str | None = None, fan: bool | str = False,
                  loops: str | None = None) -> dict:
    """Each part's replay (what the model says it was) and projection (what it says comes next),
    where the model works it out: an integrated stock, a flow or auxiliary with an equation. With
    ``whatif``, the same with other values for some parameters, beside it (nothing is kept); with
    ``fan``, the projection's spread over the parameters the model says are uncertain. ``loops``: the projection
    with the loops running (``closed``, the default where the model has controllers) or held (``held``)."""
    inputs = "trend" if inputs == "trend" else "hold"
    spec = spec_of(p)
    loops = loops_of(spec, loops)
    mr = model_run(live, p, snap, out["points"], inputs, loops=loops)
    if mr is None:
        return out
    run, proj = mr["run"], mr["projection"]
    try:
        tried, other = split_whatif(spec, whatif)
    except pr.ProposalError as e:
        tried, other, out["whatif_error"] = {}, cl.WhatIf(), str(e)
    if other and loops != "closed":
        out["whatif_error"] = (f"{', '.join(other.said())}: an input's rate, a setpoint or a pool is tried only with the loops "
                               f"running")
        other = cl.WhatIf()
    mw = model_run(live, p, snap, out["points"], inputs, tried, mr["horizon"], loops, other) if (tried or other) else None
    rk = risk_of(live, p, snap, mr, inputs) if fan and loops == "closed" else None
    if fan and loops == "closed" and rk is None:
        out["fan_pending"] = True                   # being worked out: the strip asks again, and draws no spread till then
    fn = rk if loops == "closed" else fan_of(live, p, snap, mr, inputs) if fan else None
    rf = replay_fan_of(live, p, snap, mr) if fan == "replay" else None
    for s in out["series"]:
        ref = s["ref"]
        if ref in run.how:
            s["replay"] = _round(run.values[ref])
            s["projection"] = _round(proj.values.get(ref) or [])
            s["modelled"] = run.how[ref]
            if mw is not None and ref in mw["run"].how:
                s["whatif_replay"] = _round(mw["run"].values[ref])
                s["whatif_projection"] = _round(mw["projection"].values.get(ref) or [])
            rb = (rf or {}).get("bands", {}).get(ref)
            if rb and any(a is not None and b is not None and b > a for a, b in zip(rb["p25"], rb["p75"], strict=True)):
                s["replay_fan"] = {k: _round(v) for k, v in rb.items()}
            band = (fn or {}).get("bands", {}).get(ref)
            lo, hi = ("p5", "p95") if band and "p5" in band else ("p25", "p75")
            if band and max(b - a for a, b in zip(band[lo], band[hi], strict=True)) > 0:   # a spread to draw
                s["fan"] = {k: _round(v) for k, v in band.items()}
    for s in out["series"]:                         # a flow a machine block moves: its identified model's projection
        ref = s["ref"]
        if ref not in run.how and loops == "closed" and ref in proj.values:
            s["projection"] = _round(proj.values[ref])
            s["modelled"] = "identified model"
            if mw is not None and ref in mw["projection"].values:
                s["whatif_projection"] = _round(mw["projection"].values[ref])
            band = (fn or {}).get("bands", {}).get(ref)
            if band and max(b - a for a, b in zip(band["p25"], band["p75"], strict=True)) > 0:
                s["fan"] = {k: _round(v) for k, v in band.items()}
    if any("replay" in s or "projection" in s for s in out["series"]):
        honest(live, p, snap, spec, out)
        out["projection_times"] = [round(t, 3) for t in proj.times]
        out["horizon"] = mr["horizon"]
        out["inputs"] = "; ".join(mr["projection"].notes)
        out["replay_notes"] = run.notes + run.invalid
        out["loops"] = loops
        out["loops_can_close"] = cl.has_controllers(spec)
        if loops == "closed":
            mine = {s["ref"] for s in out["series"]}
            near = mine | {f"stock.{x}" for r in mine if r.startswith("flow.") for f in [spec.flows.get(r[5:])] if f
                           for x in (f.source, f.target) if x}
            out["models"] = [{"block": x.block, "said": x.said(), "assumed": bool(x.assumed),
                              "pool": x.servers if x.form == "servers" else None}
                             for r, x in sorted(mr["models"].items()) if r in near or f"stock.{x.source}" in mine]
            out["models_assumed"] = sorted({x.block for x in mr["models"].values() if x.assumed})
            if rk is not None:
                out["risk"] = [{"goal": g.name, "said": cl.risk_said(rk, g.name), "p_off_end": rk["goals"][g.name]["p_off_end"]}
                               for g in spec.goals.values() if str(g.of) in mine and g.name in rk["goals"]]
        if tried or other:
            out["whatif"] = [{"name": k, "value": v, "was": spec.parameters[k].value, "unit": spec.parameters[k].unit,
                              "duration": spec.parameters[k].duration} for k, v in tried.items()]
            out["whatif"] += [{"name": w, "value": None, "said": w} for w in other.said()]
            if mw is not None:                      # what they break: a blow-up, or a fault the model as written has not
                faults = {r: {w: k for w, k in got.items() if k > (run.faults.get(r) or {}).get(w, 0)}
                          for r, got in {**mw["projection"].faults, **mw["run"].faults}.items()}
                bad = mw["run"].invalid + mw["projection"].invalid + pr.faults_said({r: g for r, g in faults.items() if g})
                if bad:
                    out["whatif_invalid"] = bad
        if rk is not None:                          # the closed loop's Monte Carlo: what it sampled, its runs
            if rf is not None:
                out["replay_fan"] = {"samples": rf["samples"], "invalid": rf["invalid"], "tails": rf["samples"] >= sens.TAILS}
            out["fan"] = {"samples": rk["runs"], "invalid": rk["invalid"], "tails": rk["tails"], "closed": True,
                          "parameters": [{k: v for k, v in u.items() if k in SAMPLED_KEYS} for u in rk["sampled"]],
                          "joint": "", "stopped": rk["stopped"], "seconds": rk["seconds"]}
        elif fn is not None:                          # the parameters sampled that these parts depend on
            mine = sens.upstream(spec, [s["ref"] for s in out["series"] if "replay" in s])
            sampled = [u for u in fn["parameters"] if u["name"] in mine]
            if rf is not None:
                out["replay_fan"] = {"samples": rf["samples"], "invalid": rf["invalid"], "tails": rf["samples"] >= sens.TAILS}
            out["fan"] = {"samples": fn["samples"], "invalid": fn["invalid"], "tails": fn["samples"] >= sens.TAILS,
                          "parameters": [{k: v for k, v in u.items() if k != "corr"} for u in sampled], "joint": sens.joint_said(sampled)}
    return out


def honest(live, p, snap: dict, spec, out: dict) -> None:
    """A projection resting on parts that fit badly says so in front (``low_confidence``), as the impact report does, and
    is drawn with a wider band: each charted stock that fits worse than its mean (skill < 0, on the reference window), and
    each goal on them whose loop the record does not identify (``loop-not-identifiable``)."""
    from ..control.proposals import unidentified
    mine = {s["ref"] for s in out["series"]}
    mine |= {f"stock.{x}" for r in list(mine) if r.startswith("flow.") and (f := spec.flows.get(r[5:])) for x in (f.source, f.target) if x}
    rf = reference(live, p, snap) or {}
    said = [f"the model fits {r[6:]} worse than its mean (skill {st['skill']:.2g})"
            for r, st in sorted(((rf.get("fit") or {}).get("stocks") or {}).items())
            if r in mine and st.get("skill") is not None and st["skill"] < 0]
    said += [f"{g}'s model {x['poor'][0]}" for g, x in sorted(unidentified(p, spec).items())
             if str(spec.goals[g].of) in mine and x.get("poor")]
    if not said:
        return
    out["low_confidence"] = "; ".join(said)
    for s in out["series"]:
        pj, got = s.get("projection") or [], [(a, b) for a, b in zip(s.get("values") or [], s.get("replay") or [], strict=False)
                                               if a is not None and b is not None]
        if not pj or not got:
            continue
        e = (sum((a - b) ** 2 for a, b in got) / len(got)) ** 0.5    # the replay's own error, about the projection
        fan, wide = s.get("fan") or {}, {}                          # its own spread, if any, widened by that error
        for k, m in (("p5", -2), ("p25", -0.67), ("p75", 0.67), ("p95", 2)):
            fk = fan.get(k) or []
            wide[k] = [None if v is None else (fk[i] if i < len(fk) and fk[i] is not None else v) + m * e for i, v in enumerate(pj)]
        s["fan"] = wide
        s["fan_wide"] = True


def whatif_fit(live, p, snap: dict, whatif: str | None) -> dict:
    """``GET /api/whatif-fit?whatif=a:1,b:2``: the values tried, their fit before and after on the reference
    window (per stock, and the payoff), and what would refuse them as a proposal or be said with it. Nothing
    is stored."""
    spec = spec_of(p)
    if spec is None:
        return {}
    raw = {}
    for part in (whatif or "").split(","):
        if ":" in part:
            k, _, v = part.partition(":")
            raw[k.strip()] = v.strip()
    raw = {k: v for k, v in raw.items() if not k.startswith(("flow.", "goal.", "block."))}   # tried with the loops running only
    if not raw:
        return {}
    key = ("whatif-fit", round(snap["at"] / 15), live.mtime, tuple(sorted(raw.items())))
    got = live.cached(key)
    if got is None:
        try:
            got = pr.whatif_fit(p, raw, {"at": snap["at"]})
        except pr.ProposalError as e:
            got = {"error": str(e)}
        live.keep(key, got)
    return got


def loop_dominance(live, p, snap: dict, n: int = series.POINTS, loop: str | None = None) -> dict | None:
    """Which loops drive the behaviour over the page's window (dominance.py, the Loops That Matter method,
    on the replay at its integration step): per stock, each scored loop's relative score per bucket and which
    dominates; with ``loop``, only the stocks it runs through, each with every scored loop competing there. With
    ``aggregate``: each system's stocks that are candidates to aggregate over this window (aggregation.py)."""
    mr = model_run(live, p, snap, n)
    if mr is None:
        return None
    key = ("dominance", snap["window"], snap["at"] if not snap.get("live", True) else round(snap["at"] / 5), live.mtime, n)
    got = live.cached(key)
    if got is None:
        got = dm.dominance(spec_of(p), mr["data"])
        live.keep(key, got)
    mine = {s: x for s, x in got["stocks"].items() if loop is None or loop in x["loops"]}
    groups = ag.candidates(spec_of(p), got) or {}
    return {"aggregate": [{"system": k, **g} for k, gs in sorted(groups.items()) for g in gs],
            "times": [round(t, 3) for t in got["times"]], "since": mr["data"].grid.since, "until": mr["data"].grid.until,
            "loop": loop, "polarity": got["polarity"], "assumed": got["assumed"].get(loop, []) if loop else got["assumed"],
            "not_scored": got["not_scored"] if loop is None else {k: v for k, v in got["not_scored"].items() if k == loop},
            "stocks": [{"stock": s, "loops": len(x["loops"]), "scored": len(x["scored"]), "named": x["named"], "ties": x["ties"],
                        "relative": {k: _round(v) for k, v in x["relative"].items()}, "share": x["share"],
                        "dominant": x["dominant"], "tied": x["tied"], "steps": x["steps"]} for s, x in sorted(mine.items())],
            "integration_steps": got["integration_steps"]}


def parameter_rows(p, spec, names: list[str]) -> list[dict]:
    """Each parameter an equation names: its value and where it comes from (declared, estimated or
    unknown), and its estimate beside it when there is one."""
    est = es.load(p, spec)
    kept = es.load_all(p, spec)
    rows = []
    for nm in names:
        x = spec.parameters.get(nm)
        if x is None:
            continue
        e = est.get(nm)
        def outside(v, rg=x.range):
            return bool(rg and v is not None and not rg[0] <= v <= rg[1])
        calibrated = [{"scope": c.get("scope"), "scope_words": c.get("scope_words"), "value": c.get("value"), "n": c.get("n"),
                       "n_eff": c.get("n_eff"), "when": c.get("when"),
                       "se": es.said_se(c, c["value"]) if c.get("value") is not None else None,
                       "outside_range": outside(c.get("value")), "at_range": c.get("at_range"),
                       "note": c.get("refused") or c.get("why")}
                      for which in ("parts", "systems", "whole") for k, c in sorted(kept.get(which, {}).items())
                      if c.get("parameter", k) == nm]
        rows.append({"name": nm, "value": x.value, "unit": x.unit, "provenance": x.provenance, "estimate": x.estimate,
                     "duration": x.duration,
                     "table": x.table, "description": x.description,
                     "inferred": ({"from": x.inferred if "/" in x.inferred else None} if x.inferred else None),
                     "where": str(x.defined) if x.defined else None,
                     "estimated": None if not e or e.get("value") is None else
                     {**{k: e.get(k) for k in ("value", "n", "when", "window", "before", "after", "held_before", "held_after",
                                                "fitted_to", "at_bound", "at_range", "corr", "slowest", "n_eff")},
                      "se": es.said_se(e, e["value"]), "outside_range": outside(e.get("value"))},
                     "estimate_note": (e.get("why") if e and e.get("value") is None else e.get("refused") if e else None),
                     "calibrated": calibrated, "range": list(x.range) if x.range else None})
    return rows


def exercised(live, p, snap: dict) -> list[dict]:
    """The parts the record has not exercised (``numbers/exercised.py``) and the equations that fit it worse than their
    mean (``fit.worse_than_mean``), as findings: ``{level, code, about,
    message}``, on the reference window as of the page's moment; kept a minute."""
    from ..numbers import exercised as ex
    spec = spec_of(p)
    if spec is None:
        return []
    key = ("exercised", snap["at"] if not snap.get("live", True) else round(snap["at"] / 60), live.mtime)
    got = live.cached(key)
    if got is None:
        try:
            _, q = ex.of_project(p, spec, snap["at"])
        except Exception:                            # a record that cannot be read says nothing here
            q = {}
        got = [{"level": "warn", "code": ex.CODE, "about": ref, "message": ex.said(x)} for ref, x in sorted(q.items())]
        try:                                         # and each equation that fits worse than its mean (calibration per part)
            got += [{"level": "warn", "code": "calibration-worse-than-mean", "about": ref, "message": msg}
                    for ref, msg in ft.worse_than_mean(spec, reference(live, p, snap)["fit"])]
        except Exception:
            pass
        live.keep(key, got)
    return got


def coherence(live, p, snap: dict, window: float | None = None) -> dict:
    """The coherence check (``coherence.py``) as of the page's moment, over the last day (or ``window``); kept a
    minute."""
    from .. import coherence as co
    spec = spec_of(p)
    if spec is None:
        return {"kinds": {}, "findings": [], "pairs": co.PAIRS}
    key = ("coherence", snap["at"] if not snap.get("live", True) else round(snap["at"] / 60), live.mtime, window)
    got = live.cached(key)
    if got is None:
        try:
            got = co.of_project(p, spec, window or co.WINDOW, None if snap.get("live", True) else snap["at"])
        except Exception as e:                       # a record that cannot be read says nothing here
            got = {"kinds": {}, "findings": [], "pairs": co.PAIRS, "error": f"{type(e).__name__}: {e}"}
        got["scores"] = {k: co.score_line(k, x) for k, x in got["kinds"].items()}
        live.keep(key, got)
    return got


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
    kept = es.load_all(p, spec)
    names = sorted(n for n, x in spec.parameters.items() if x.estimate and not x.table)
    not_proposed = {}
    for which in es.SCOPES:
        for k, e in sorted(kept.get(which, {}).items()):
            n = e.get("parameter", k)
            if n in spec.parameters and (e.get("refused") or e.get("why")):
                label = es.label(k, e)
                not_proposed[label] = e.get("refused") or e.get("why")
    from ..numbers import memory as mem
    for x in reversed(mem.turned(p, spec)):                 # turned away by the gate or the judge, newest last: it wins
        for t in str(x.get("target") or "").split(", "):
            if t.startswith("parameter.") and t[10:] in names:
                not_proposed[t[10:]] = f"{x['state']}: {x['why']}" + (f"; {x['held_back']}" if x.get("held_back") else "")
    return {"version": ver.version(spec), "structure": ver.structure(spec), "since": rf["data"].grid.since,
            "until": rf["data"].grid.until, "total": ft._slim(fit["total"]), "stocks": rows("stocks"),
            "accounting": rows("accounting"), "equations": rows("equations"), "partial": rows("partial"),
            "judged_by_stock": fit["judged_by_stock"], "invalid": fit["invalid"],
            "notes": rf["run"].notes, "words": ft.WORDS, "min_points": ft.MIN_POINTS,
            "history": ft.versions(p), "accepted": pr.accepted(p), "proposals": pr.pending(p, spec),
            "modelling": _modelling(p),
            "estimated_at": max((e.get("when") or 0 for got in kept.values() for e in got.values()), default=None) or None,
            "to_estimate": names,
            "open_loops": es.open_loops(spec), "open_said": es.open_said(es.open_loops(spec)),
            "calibrations": [{"key": w, "words": es.scope_words(spec, w), "count": len(es.scopes(spec, names, w)) if names else 0,
                              "when": max((e.get("when") or 0 for e in kept.get(w, {}).values()), default=None) or None}
                             for w in es.SCOPES],
            "not_proposed": not_proposed, "readiness": readiness(spec, rf, names),
            "residuals": snap.get("residuals", {}), **queue(live, p, snap)}


def readiness(spec, rf: dict, names: list[str]) -> dict:
    """For the Model page's "What's available": each parameter to estimate, the parts whose equations use it
    (where its what-if and calibrations are), and whether the reference window is long enough yet for a
    proposal: three of the slowest time constant it touches, and forty points fitted (``estimate.judged``);
    the rest (independent errors, told apart, held out) is said once it is calibrated."""
    out = {}
    data = rf["data"]
    span = data.grid.until - data.grid.since
    cut = max(1, int(round(data.grid.n * (1 - es.HOLD_OUT))))
    for n in names:
        owners, stocks = es.touched(spec, {n})
        tc = es.slowest(spec, rf["run"], owners, stocks, rf["data"])
        uses = sorted(r for r in owners if (r.startswith("flow.") and r[5:] in spec.flows and spec.flows[r[5:]].equation
                                              and n in spec.flows[r[5:]].equation.parameters)
                      or (r.startswith("auxiliary.") and r[10:] in spec.auxiliaries and spec.auxiliaries[r[10:]].equation
                          and n in spec.auxiliaries[r[10:]].equation.parameters))
        refs = owners | {f"stock.{s}" for s in stocks}
        points = sum(1 for r in refs for i, v in enumerate(data.values.get(r) or []) if v is not None and i < cut)
        out[n] = {"parts": uses, "span": span, "points": points, "points_needed": es.PROPOSE, "slowest": tc * 3600 if tc else None,
                  "needs": ft.COVER * tc * 3600 if tc else None, "range": bool(spec.parameters[n].range)}
    return out


def _modelling(p) -> dict | None:
    try:
        from ..numbers import modelling_status as mst
        return mst.of(p)
    except Exception:
        return None


def _structural(live, p, snap: dict) -> list[dict]:
    """The structural proposals looked for again (at most every few minutes, or when the model changes):
    what was found and could not be made."""
    spec = spec_of(p)
    key = ("structural", live.mtime, round(snap["at"] / rv.STRUCTURAL_EVERY))
    got = live.cached(key)
    if got is None:
        got = rv.refresh(p, spec, None if snap.get("live", True) else snap["at"]) if snap.get("live", True) else []
        live.keep(key, got)
    return got


LOOPS = threading.Lock()
LOOPS_SEEN: dict = {}            # goal → (model mtime, when analysed)


def _analyse_loops(live) -> None:
    """Each loop analysed in turn, in the background, so its proposals (a process, a gain) join the queue."""
    if not LOOPS.acquire(blocking=False):
        return

    def work():
        try:
            from .control_api import get as control
            p = live.get()
            spec = spec_of(p)
            for g in list(spec.goals) if spec else []:
                seen = LOOPS_SEEN.get(g)
                if seen and seen[0] == live.mtime and time.time() - seen[1] < 300:
                    continue
                try:
                    control(live, p, {"at": time.time(), "live": True}, g)
                except Exception:                       # a loop that cannot be analysed offers nothing
                    pass
                LOOPS_SEEN[g] = (live.mtime, time.time())
        finally:
            LOOPS.release()
    threading.Thread(target=work, name="ergostat-loops", daemon=True).start()


def queue(live, p, snap: dict) -> dict:
    """The review queue (``numbers/review.py``): every change waiting, each with what, where, why, how it
    was found, its benefit and the exact diff; and what ergostat can and cannot propose yet."""
    spec = spec_of(p)
    not_made = _structural(live, p, snap)
    if snap.get("live", True):
        _analyse_loops(live)
    control = rv.control_pending(p, spec)
    goals = list(spec.goals)
    from ..numbers import improve as im
    from ..numbers import memory as mem
    not_made = list(not_made) + [{"title": f"{x['title']} (proposed by {x['by']})", "why": x["why"] + (
                                      f"; {x['held_back']}" if x.get("held_back") else ""), "code": "proposed",
                                  "by": x["by"]} for x in im.not_proposed(p)[:12]]
    not_made += [{"title": x["title"], "why": f"{x['state']}: {x['why']}" + (f"; {x['held_back']}" if x["held_back"] else ""),
                  "code": "turned-away", "by": x["by"], "item": x["item"]}
                 for x in mem.turned(p, spec) if x["by"] == "ergostat"][:12]
    from ..numbers import redesign as rd
    return {"queue": rv.entries(p, spec, control), "not_made": not_made,
            "redesigns": {"systems": ["model", *sorted(spec.systems)], "asked": rd.asked(p), "last": rd.last(p),
                          "settings": rd.settings(spec), "on": "redesigner" in spec.blocks},
            "loops_analysed": sum(1 for g in goals if (LOOPS_SEEN.get(g) or (None,))[0] == live.mtime), "loops": len(goals),
            "can": [{"what": a, "how": b} for a, b in rv.stc.CAN], "cannot": rv.stc.CANNOT}


_PROPOSED: dict = {}             # (change, model files' mtime) → the model it would leave


def proposed_graph(live, p, q: dict, pid: str, draw) -> dict:
    """``GET /api/graph?proposal=ID&view=...``: the diagram of the model as a change waiting would leave it (its edit
    applied in memory, nothing written), with what it adds, changes and takes away (``proposed``), so the page draws
    the new and changed parts dashed and names the parts it takes away. Its views are the model's: dynamics and
    blocks."""
    from .. import model as mdl
    from ..numbers import changeset as cs
    from ..numbers import trial as tr
    from ..spec.load import texts as override
    x = pr.stored(p).get(pid)
    if x is None:
        return {"error": f"no change {pid}"}
    key = (pid, live.mtime)
    got = _PROPOSED.get(key)
    if got is None:
        try:
            texts = tr.texts_after(tr.edits_of(x))
            with override(texts):
                m2 = mdl.load(p.model.path.parent)
        except (tr.TrialError, Exception) as e:          # an edit that no longer applies draws nothing
            return {"error": f"it cannot be drawn: {e}", "nodes": [], "edges": []}
        if m2.spec is None or [e for e in m2.problems if e.level == "error"]:
            return {"error": "the model it leaves does not compile", "nodes": [], "edges": []}
        marks = cs.parts_changed(p.model.spec, m2.spec)
        if len(_PROPOSED) > 8:
            _PROPOSED.clear()
        got = _PROPOSED[key] = (m2, marks)
    m2, marks = got
    out = draw(m2)
    if isinstance(out, dict):
        renamed = [r.split(" → ")[1] for r in marks.get("renamed") or []]
        said = ("drawn as the change would leave the model; what needs attention is said of the model as it is (the "
                "diagram without it)")
        out = {**out, "_model": m2, "attention": [{"level": "hint", "what": "a proposal", "says": said}],
               "proposed": {"id": pid, "title": x.get("title"), "kind": x.get("kind"),
                                                 "state": x.get("state"), "added": marks["added"],
                                                 "changed": sorted(set(marks["changed"]) | set(renamed)),
                                                 "renamed": marks["renamed"], "removed": marks["removed"]}}
    return out


def effect(live, p, snap: dict, ids: str | None) -> dict:
    """``GET /api/proposal-effect?ids=a,b``: the changes simulated together, in memory (nothing written)."""
    spec = spec_of(p)
    if spec is None:
        return {}
    want = [x for x in (ids or "").split(",") if x]
    key = ("effect", tuple(want), live.mtime, round(snap["at"] / 30))
    got = live.cached(key)
    if got is not None:
        return got
    pending = pr.pending(p, spec) + rv.control_pending(p, spec)
    xs = [x for w in want for x in pending if x["id"] == w]
    if not xs:
        return {"error": "no such proposal waiting"}
    lkey = ("leverage", live.mtime, round(snap["at"] / 120))
    base = live.cached(lkey)
    if base is None:
        try:
            base = rv.base_leverage(p, spec) or {}
        except Exception:
            base = {}
        live.keep(lkey, base)
    got = rv.effect(p, spec, xs, None, base or None, most=rv.CHARTS if len(xs) == 1 else rv.CHARTS_ALL)
    live.keep(key, got)
    return got


def redesign_asked(live, p, system: str) -> tuple[int, dict]:
    """The owner asks for a redesign: recorded (``ergostat.model.redesign-asked``), for the redesigner block to take
    up on its next run; what it makes joins the review queue. Nothing runs in the page server."""
    from ..numbers import redesign as rd
    try:
        s = rd.system_of(p.model.spec, system)
    except ValueError as e:
        return 400, {"error": str(e)}
    w = rd.waiting(p, p.model.spec, s)
    if w is not None:
        return 409, {"error": f"a redesign of {s} is waiting already: in the queue below", "id": w["id"]}
    if "redesigner" not in p.model.spec.blocks:
        return 409, {"error": "no redesigner in the model: use: modelling with ai: true has one"}
    got = rd.ask(p, s, by=who())
    return 200, {"asked": got["asked"], **rd.settings(p.model.spec)}


def post(live, path: str, window: float, q: dict | None = None) -> tuple[int, dict]:
    """``POST /api/estimate?calibrate=parts|systems|whole`` (calibrate, and make the proposals),
    ``/api/propose?whatif=NAME:V,NAME:V`` (the owner's what-if, every value tried made one proposal; or
    ``parameter=NAME&value=V``),
    ``/api/proposals/ID/accept`` and ``/api/proposals/ID/dismiss``: the page's only writes, each the
    owner's own act, and none of them changes the model but Accept."""
    q = q or {}
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
                which = (q.get("calibrate") or ["parts"])[0]
                if which not in es.SCOPES:
                    return 400, {"error": f"calibrate: one of {', '.join(es.SCOPES)}"}
                return 200, {"proposals": pr.make(p, snap, which=which)}
            finally:
                ESTIMATING.release()
        if parts == ["propose"]:
            if q.get("whatif"):                     # every value tried together, as the charts drew them
                raw = dict(x.split(":", 1) for x in q["whatif"][0].split(",") if ":" in x)
                return 200, pr.propose_values(p, {k.strip(): v.strip() for k, v in raw.items()}, snap)
            return 200, pr.propose_value(p, (q.get("parameter") or [""])[0], (q.get("value") or [""])[0], snap)
        if parts == ["redesign"]:                    # the owner asks for a redesign (the Model page's button)
            return redesign_asked(live, p, (q.get("system") or ["model"])[0])
        if len(parts) == 3 and parts[0] == "proposals" and parts[2] in ("accept", "dismiss"):
            reason = (q.get("reason") or [""])[0] or None
            expect = (q.get("expect") or [""])[0] or None
            if parts[1] in {x["id"] for x in rv.control_pending(p, spec_of(p))}:     # a loop's process or gain
                from ..control import proposals as cp
                from .control_api import forget
                try:
                    got = (cp.dismiss(p, parts[1], reason, by=who()) if parts[2] == "dismiss"
                           else cp.accept(p, parts[1], by=who(), expect=expect))
                except cp.ProposalError as e:
                    return 409, {"error": str(e)}
                if parts[2] == "accept":
                    live.reloaded()
                forget(live)
                return 200, got
            if parts[2] == "dismiss":
                return 200, pr.dismiss(p, parts[1], reason, by=who())
            got = pr.accept(p, parts[1], snap, by=who(), expect=expect)
            live.reloaded()
            return 200, got
    except pr.ProposalError as e:
        return 409, {"error": str(e)}
    return 404, {"error": "not found"}
