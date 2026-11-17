"""The review queue: every change to the model waiting for the owner, read the way a pull request is
read. Each entry answers, in this order:

- **what**: the kind of change in words (a parameter's value, an equation, a new stock with its flows, a
  link removed, a loop's process, a controller's gain);
- **where**: the parts it touches (what the shared selection lights in both diagrams), and the file and
  line it edits;
- **why**: the evidence, in plain words, from the fit, the residuals, the identification or the check;
- **how found**: the method, named plainly, with its data span and how sure it is;
- **effect** (``effect``): the affected parts' record, the model's line as it is and with the change, and
  how the projection changes, simulated with the change applied in memory (``trial.py``), never in the file;
- **benefit**: the fit before and after, and what changes operationally: a projection, a time to a limit,
  a goal held or not, a stability margin, and the leverage of the flows it touches;
- **diff**: exactly what Accept writes, as a unified diff, and its hash (an Accept carries it back, and
  is refused if the files would now be written otherwise).

Several entries can be simulated together (``effect`` with several ids): their edits applied together,
each conflicting one (the same lines, the same parameter, the same equation) left out and said."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from ..durations import human as dur
from ..spec.ir import Spec
from . import estimate as es
from . import leverage as lv
from . import observe as ob
from . import proposals as pr
from . import simulate as sim
from . import structural as stc
from . import trial as tr
from . import version as ver
from . import yamledit as ye

STRUCTURAL_EVERY = 600.0        # the record-based structural proposals are looked for again at most this often
CHART_POINTS = 120
CHARTS = 4                      # an entry's chart shows at most this many parts; all pending together, six
CHARTS_ALL = 6
STATE = "structural.json"


# ---- the structural proposals, kept with the others (so Accept and Dismiss work the same)

def _estimates(p, spec: Spec) -> dict:
    out: dict = {}
    kept = es.load_all(p, spec)
    for which in ("whole", "systems", "parts"):                 # each part alone's first
        for k, e in kept.get(which, {}).items():
            if e.get("value") is not None:
                out[e.get("parameter", k)] = {**e, "se": es.said_se(e, e["value"])}
    return out


def refresh(p, spec: Spec, at: float | None = None, force: bool = False) -> list[dict]:
    """Look for structural proposals for the model as it is (again, when its version changed or a while
    has passed), store the new ones as pending, let go of pending ones no longer found; return what was
    found and could not be made."""
    f = p.dir / STATE
    try:
        kept = json.loads(f.read_text())
    except (OSError, ValueError):
        kept = {}
    v = ver.version(spec)
    now = at or time.time()
    if not force and kept.get("version") == v and now - kept.get("at", 0) < STRUCTURAL_EVERY:
        return kept.get("not_made", [])
    data = ob.measured(p, ob.reference(p, at))
    run, base = tr.fit_of(spec, data)
    found, not_made = stc.find(p, spec, data, _estimates(p, spec), base)
    props = pr.stored(p)
    st = ver.structure(spec)
    mine = {x["id"] for x in found}
    for k in [k for k, x in props.items() if x.get("kind") == "structure" and x["status"] == "pending" and
              (k not in mine or x.get("structure") != st)]:
        del props[k]
    for x in found:
        if x["id"] in props:                           # dismissed (or accepted, or pending) already: not made again
            continue
        try:
            after_spec = tr.spec_after(p, tr.edits_of(x))
            _, after = tr.fit_of(after_spec, ob.measured(p, data.grid, after_spec))
        except tr.TrialError:
            after = None
        props[x["id"]] = {**x, "fit_before": base, "fit_after": after or {"total": None, "stocks": {}, "equations": {}},
                          "status": "pending", "created": now, "structure": st, "version": v,
                          "window": data.grid.until - data.grid.since, "span": data.grid.until - data.grid.since}
    pr.save(p, props)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": v, "at": now, "not_made": not_made}, indent=1))
    tmp.replace(f)
    return not_made


# ---- an entry

def _words(ref: str) -> str:
    kind, _, name = ref.partition(".")
    return f"{kind} {name}"


def selectable(spec: Spec, parts: list[str]) -> list[str]:
    """The parts the shared selection can hold (correspond.universe): a parameter is lit through the
    equations that use it; a part a change adds is not drawn yet."""
    from ..correspond import universe
    have = set(universe(spec))
    out: list[str] = []
    for r in parts:
        if r.startswith("parameter."):
            out += pr.users_of(spec, r.split(".", 1)[1])
        else:
            out.append(r)
    return [r for r in dict.fromkeys(out) if r in have]


def _what(x: dict) -> str:
    k = x.get("kind")
    if k == "parameter":
        n = len(x.get("parameters") or {})
        what = "A parameter's value" if n == 1 else f"{n} parameters' values, fitted together"
        return what + (", your what-if" if x.get("scope") == "what-if" else "")
    if k == "equation":
        return "An equation for a flow that has none"
    if k == "structure":
        c = x.get("change") or "a change to the structure"
        return c[0].upper() + c[1:]
    if k == "process":
        return ("A loop's process: an integrator with dead time" if (x.get("values") or {}).get("form") == "integrating"
                else "A loop's process: first order with dead time")
    if k == "tuning":
        return "A controller's gain" + (", detuned for robustness" if "detuned" in x.get("title", "") else ", tuned by SIMC")
    return "A change"


def _span_of(x: dict) -> float | None:
    for k in ("span", "window"):
        if x.get(k):
            return x[k]
    est = next(iter((x.get("estimate") or {}).values()), None)
    return est.get("window") if est else None


def _how(x: dict, spec: Spec) -> dict:
    """The method, named plainly, its data span, its points, and how sure it is."""
    k = x.get("kind")
    span = _span_of(x)
    if k == "parameter" and x.get("scope") == "what-if":
        return {"method": "not estimated: values you tried as a what-if, judged on the replay", "span": span, "n": None,
                "confidence": "; ".join(x.get("warnings") or []) or None}
    if k == "parameter":
        e = next(iter((x.get("estimate") or {}).values()), {}) or {}
        n = e.get("n")
        sure = []
        for name, v in (x.get("parameters") or {}).items():
            se = (x.get("uncertainty") or {}).get(name)
            if se is not None and v:
                sure.append(f"{name} ± {abs(se / v):.0%} (one standard error)")
        held = (x.get("objective") or {})
        if held.get("held_before") and held.get("held_after") is not None:
            sure.append(f"on the record held out its weighted error falls {1 - held['held_after'] / held['held_before']:.0%}")
        return {"method": f"weighted least squares on the replay ({x.get('scope_words') or 'each part alone'}), searched by "
                          f"Nelder–Mead, the last fifth of the record held out", "span": span, "n": n,
                "confidence": "; ".join(sure) or None}
    if k == "equation":
        import re
        m = re.search(r"explain (\d+)%.*?(\d+) points", x.get("reason", ""))
        sure = [f"its causes explain {m.group(1)}% of its readings"] if m else []
        if "biased" in x.get("reason", ""):
            sure.append("inside a loop a controller closes, so biased: a start, not a measurement")
        return {"method": "ordinary least squares of the flow's readings on its declared causes", "span": span,
                "n": int(m.group(2)) if m else None, "confidence": "; ".join(sure) or None}
    if k == "structure":
        on_record = x.get("code", "").startswith(("simplify", "no-effect", "sign", "stock-without"))
        return {"method": x.get("method"), "span": span if on_record else None,
                "n": None, "confidence": None}
    if k == "process":
        r = x.get("identified") or {}
        moves = r.get("moves")
        src = "a step test, open loop" if r.get("test") else "the loop working, closed loop"
        return {"method": (f"output-error identification of {'an integrator' if r.get('form') == 'integrating' else 'a first-order'} "
                           f"process with dead time (Ljung) from {moves} step change{'s' if moves != 1 else ''} of u, "
                           f"from {src}") if moves is not None else "output-error identification (Ljung)",
                "span": r.get("span"), "n": r.get("n_est"),
                "confidence": (f"follows {r['fit_val']:.0f}% of the record held out" if r.get("fit_val") is not None else None)}
    if k == "tuning":
        return {"method": "Skogestad's SIMC rules (2003) for the process the model holds, checked to settle with margins",
                "span": None, "n": None, "confidence": None}
    return {"method": None, "span": span, "n": None, "confidence": None}


def _why(x: dict, spec: Spec) -> str:
    """The evidence, in plain words."""
    k = x.get("kind")
    if k == "parameter":
        bits = []
        for r in x.get("touched") or []:
            s = ((x.get("fit_before") or {}).get("stocks") or {}).get(r) or ((x.get("fit_before") or {}).get("equations") or {}).get(r)
            if s and s.get("says"):
                bits.append(f"as written, the replay of {r.split('.', 1)[1]} {s['says']}")
        if x.get("scope") == "what-if":
            return "; ".join(bits + ["you tried these values"]) + "."
        o = x.get("objective") or {}
        fall = 1 - o["after"] / o["before"] if o.get("before") and o.get("after") is not None else None
        moved = []
        for n, v in (x.get("parameters") or {}).items():
            was = (x.get("previous") or {}).get(n)
            se = (x.get("uncertainty") or {}).get(n)
            if was is not None and se:
                moved.append(f"{n}'s estimate is {abs(v - was) / se:.0f} standard errors from the value written")
        return "; ".join(bits + moved + ([f"with it the weighted error on what it was fitted to falls {fall:.0%}"]
                                          if fall is not None else [])) + "."
    if k == "equation":
        t = (x.get("target") or "").split(".", 1)[1]
        return (f"{t} has declared causes and no equation, so the model cannot work it out and takes it as measured; "
                + x.get("reason", "") + ".")
    if k in ("process", "tuning"):
        return x.get("reason", "").split(". ")[0] + "."
    return x.get("reason", "")


def _benefit(x: dict) -> dict:
    b, a = (x.get("fit_before") or {}).get("total") or {}, (x.get("fit_after") or {}).get("total") or {}
    per = []
    for r in x.get("touched") or []:
        fb = ((x.get("fit_before") or {}).get("stocks") or {}).get(r) or ((x.get("fit_before") or {}).get("equations") or {}).get(r)
        fa = ((x.get("fit_after") or {}).get("stocks") or {}).get(r) or ((x.get("fit_after") or {}).get("equations") or {}).get(r)
        if fb or fa:
            per.append({"ref": r, "r2_before": (fb or {}).get("r2"), "r2_after": (fa or {}).get("r2"),
                        "mape_before": (fb or {}).get("mape"), "mape_after": (fa or {}).get("mape")})
    out = {"nmse_before": b.get("nmse"), "nmse_after": a.get("nmse"), "parts": per}
    if x.get("kind") == "tuning":
        out["margins"] = x.get("reason", "").split(". ", 1)[1] if ". " in x.get("reason", "") else None
    return out


def diff_of(x: dict) -> dict:
    """Exactly what Accept writes: each file's text now and after, as a unified diff, and its hash."""
    try:
        edits = tr.edits_of(x)
        new = ye.apply_together(edits)
    except (tr.TrialError, ye.EditError) as e:
        return {"error": str(e)}
    parts = []
    for f, text in sorted(new.items()):
        old = Path(f).read_text(encoding="utf-8")
        parts.append(ye.unified(old, text, _rel(f)))
    text = "".join(parts)
    return {"unified": text, "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "files": [{"file": _rel(f), "lines": sorted({h.line for e in edits if e.file == f for h in e.hunks})} for f in sorted(new)]}


def _rel(f: str) -> str:
    try:
        return str(Path(f).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return Path(f).name


def entry(x: dict, spec: Spec, others: list[dict] | None = None) -> dict:
    parts = list(dict.fromkeys([*(x.get("parts") or []), *(x.get("touched") or [])]))
    if x.get("kind") in ("process", "tuning"):
        g = spec.goals.get(x.get("goal") or "")
        parts = [f"goal.{x['goal']}"] + ([f"{g.of.kind}.{g.of.name}"] if g else []) + \
            ([f"block.{x['block']}"] if x.get("block") else [])
    sel = selectable(spec, parts)
    d = diff_of(x)
    clash = [{"id": y["id"], "why": w} for y in (others or []) if (w := tr.conflicts(x, y))]
    simulable = x.get("kind") in ("parameter", "equation", "structure") and "error" not in d
    return {"id": x["id"], "source": "control" if x.get("kind") in ("process", "tuning") else "numbers",
            "kind": x.get("kind"), "code": x.get("code"), "what": _what(x), "title": x.get("title"),
            "where": {"parts": parts, "select": sel, "words": [_words(r) for r in parts],
                      "new": x.get("new_parts") or [], "gone": x.get("gone_parts") or [], "files": d.get("files") or []},
            "why": _why(x, spec), "how": _how(x, spec), "benefit": _benefit(x), "reason": x.get("reason"),
            "diff": d, "conflicts": clash, "simulable": simulable,
            "not_simulated": None if simulable else ("the replay takes what a controller sets as measured, so a loop's "
                                                     "process or gain changes no replay; its effect is the step response "
                                                     "and margins on the loop's panel" if x.get("kind") in ("process", "tuning")
                                                     else d.get("error")),
            "created": x.get("created"), "status": x.get("status", "pending")}


def control_pending(p, spec: Spec) -> list[dict]:
    """The loops' proposals on offer (worked out when a loop is analysed), still current and not decided."""
    from ..control import loop as lp
    from ..control import proposals as cp
    done = cp.decisions(p)
    out = []
    for x in list(cp.OFFERED.values()):
        if x["kind"] not in ("process", "tuning") or x["id"] in done or x.get("goal") not in spec.goals:
            continue
        try:
            if lp.key(spec, x["goal"]) != x["key"]:
                continue
        except Exception:
            continue
        out.append(x)
    return out


def entries(p, spec: Spec, control: list[dict] | None = None) -> list[dict]:
    xs = pr.pending(p, spec) + (control or [])
    order = {"parameter": 0, "equation": 1, "structure": 2, "process": 3, "tuning": 4}
    xs.sort(key=lambda x: (order.get(x.get("kind"), 9), x.get("created") or 0))
    return [entry(x, spec, xs) for x in xs]


def find_any(p, spec: Spec, pid: str) -> dict:
    for x in pr.pending(p, spec) + control_pending(p, spec):
        if x["id"] == pid or x["id"].startswith(pid):
            return x
    raise pr.ProposalError(f"no proposal {pid} waiting")


# ---- the effect: simulated with the change in memory

def _charted(spec: Spec, xs: list[dict], most: int) -> list[str]:
    out: list[str] = []
    for x in xs:
        refs = [*(x.get("touched") or []), *(x.get("parts") or []), *(x.get("new_parts") or [])]
        for r in refs:
            kind, _, name = r.partition(".")
            if kind == "flow" and name in spec.flows:
                f = spec.flows[name]
                refs += [f"stock.{s}" for s in (f.source, f.target) if s]
        for r in sorted(dict.fromkeys(refs), key=lambda r: (not r.startswith("stock."), r)):
            if r.split(".")[0] in ("stock", "flow", "auxiliary") and r not in out:
                out.append(r)
    return out[:most]


def _round(vs):
    return [None if v is None else round(v, 6) for v in vs or []]


def _first_past(times, vals, limit) -> float | None:
    for t, v in zip(times, vals or [], strict=False):
        if v is not None and v >= limit:
            return t
    return None


def operational(spec: Spec, refs: list[str], before: sim.Run, after: sim.Run, now: float, horizon: float) -> list[str]:
    """What changes ahead, in words: each part's projected value at the horizon, a time to its limit, a
    goal projected to hold or not."""
    out = []
    for r in refs:
        kind, _, name = r.partition(".")
        b, a = before.values.get(r), after.values.get(r)
        if not b or not a:
            continue
        bl, al = next((v for v in reversed(b) if v is not None), None), next((v for v in reversed(a) if v is not None), None)
        if bl is None or al is None:
            continue
        unit = getattr(spec.measured(kind).get(name), "unit", "") or ""
        if abs(al - bl) > 1e-9 * max(1.0, abs(bl)):
            out.append(f"{name} in {dur(horizon)}: projected {ye.number(bl)} → {ye.number(al)}{' ' + unit if unit else ''}")
        st = spec.stocks.get(name) if kind == "stock" else None
        if st is not None and st.limit is not None:
            tb, ta = _first_past(before.times, b, st.limit), _first_past(after.times, a, st.limit)
            if tb != ta:
                said = lambda t: f"in {dur(t - now)}" if t else f"not within {dur(horizon)}"   # noqa: E731
                out.append(f"{name} reaches its limit ({ye.number(st.limit)}) {said(tb)} → {said(ta)}")
        for g in spec.goals.values():
            if f"{g.of.kind}.{g.of.name}" != r:
                continue
            hb, ha = not g.hold.outside(bl, g.tolerance), not g.hold.outside(al, g.tolerance)
            if hb != ha:
                out.append(f"goal {g.name} ({g.hold}): projected {'held' if hb else 'off'} → {'held' if ha else 'off'} in {dur(horizon)}")
    return out


def _leverage(p, spec: Spec, data, run, horizon: float, flows: list[str], base: dict | None) -> list[str]:
    if not flows or not spec.goals:
        return []
    got = lv.rank(spec, data, run, horizon, flows=flows)
    rows = got["rows"]
    if base:                                          # placed among the other flows as the model is now
        others = [r for r in base["rows"] if r["flow"] not in flows]
        allr = sorted(others + rows, key=lambda r: -abs(r["score"]))
        for i, r in enumerate(allr):
            r["rank"] = i + 1
        return [lv.said(r, len(allr)) for r in rows]
    return [lv.said(r, len(rows)) for r in rows]


def effect(p, spec: Spec, xs: list[dict], at: float | None = None, base_leverage: dict | None = None,
           most: int = CHARTS) -> dict:
    """The change (or changes, together) simulated: per part charted, its record, the model's replay and
    projection as it is and with the change; the fit before and after; what changes ahead; the leverage of
    the flows it touches. Nothing is written."""
    taken, left, edits = tr.combine(p, [x for x in xs if x.get("kind") in ("parameter", "equation", "structure")])
    left += [{"id": x["id"], "why": "a loop's process or gain changes no replay"} for x in xs
             if x.get("kind") not in ("parameter", "equation", "structure")]
    grid = ob.reference(p, at, CHART_POINTS)
    data = ob.measured(p, grid)
    run, fit_b = tr.fit_of(spec, data)
    out: dict = {"taken": [x["id"] for x in taken], "left": left, "since": grid.since, "until": grid.until}
    if not taken:
        return {**out, "charts": [], "operational": [], "leverage": []}
    try:
        after = tr.spec_after(p, edits)
    except tr.TrialError as e:
        return {**out, "error": str(e), "charts": [], "operational": [], "leverage": []}
    data_a = ob.measured(p, grid, after)
    run_a, fit_a = tr.fit_of(after, data_a)
    from ..web.numbers_api import horizon_of
    horizon = horizon_of(run, grid.until - grid.since)
    points = max(2, round(CHART_POINTS * horizon / max(grid.until - grid.since, 1.0)))
    proj_b = sim.project(spec, data, run, horizon, sim.plan(spec), points=points)
    proj_a = sim.project(after, data_a, run_a, horizon, sim.plan(after), points=points) if run_a.valid else None
    refs = _charted(after, taken, most) or _charted(spec, taken, most)
    charts = []
    for r in refs:
        kind, _, name = r.partition(".")
        x = after.measured(kind).get(name) or spec.measured(kind).get(name)
        charts.append({"ref": r, "name": name, "kind": kind, "unit": getattr(x, "unit", "") or "",
                       "per": kind == "flow", "new": r in {n for t in taken for n in (t.get("new_parts") or [])},
                       "gone": name not in after.measured(kind),
                       "measured": _round(data.values.get(r) or data_a.values.get(r)),
                       "before": _round(run.values.get(r)) if r in run.how else None,
                       "after": _round(run_a.values.get(r)) if r in run_a.how else None,
                       "proj_before": _round(proj_b.values.get(r)) if proj_b.values.get(r) else None,
                       "proj_after": _round(proj_a.values.get(r)) if proj_a and proj_a.values.get(r) else None})
    flows = [r.split(".", 1)[1] for t in taken for r in (t.get("touched") or []) + (t.get("parts") or [])
             if r.startswith("flow.") and r.split(".", 1)[1] in after.flows]
    lev = []
    if run_a.valid:
        try:
            lev = _leverage(p, after, data_a, run_a, horizon, list(dict.fromkeys(flows))[:6], base_leverage)
        except Exception:                                     # leverage is a help to reading, never a reason to fail
            lev = []
    return {**out, "times": [round(t, 3) for t in grid.times()], "ptimes": [round(t, 3) for t in proj_b.times],
            "horizon": horizon, "charts": charts,
            "fit_before": fit_b, "fit_after": fit_a, "valid": run_a.valid, "invalid": run_a.invalid,
            "operational": operational(after, refs, proj_b, proj_a, grid.until, horizon) if proj_a else [],
            "leverage": lev}


def base_leverage(p, spec: Spec, at: float | None = None) -> dict | None:
    if not spec.goals:
        return None
    grid = ob.reference(p, at, CHART_POINTS)
    data = ob.measured(p, grid)
    run = sim.replay(spec, data, sim.plan(spec))
    if not run.valid:
        return None
    from ..web.numbers_api import horizon_of
    return lv.rank(spec, data, run, horizon_of(run, grid.until - grid.since))


def show(e: dict) -> list[str]:
    """An entry in full, as the command line prints it (``ergostat proposals --show ID``)."""
    h = e["how"]
    out = [f"{e['id']}  {e['what']}", f"  {e['title']}",
           f"  WHERE    {', '.join(e['where']['words']) or '–'}" +
           (f"; new: {', '.join(e['where']['new'])}" if e["where"]["new"] else "") +
           (f"; removed: {', '.join(e['where']['gone'])}" if e["where"]["gone"] else ""),
           f"           {', '.join(f['file'] + ':' + ','.join(map(str, f['lines'])) for f in e['where']['files'])}",
           f"  WHY      {e['why']}",
           f"  HOW      {h.get('method') or '–'}" + (f", over {dur(h['span'])} of record" if h.get("span") else "") +
           (f", {h['n']} points" if h.get("n") else "") + (f"; {h['confidence']}" if h.get("confidence") else "")]
    b = e["benefit"]
    if b.get("nmse_before") is not None or b.get("nmse_after") is not None:
        f = lambda v: "–" if v is None else f"{v:.3g}"   # noqa: E731
        out.append(f"  BENEFIT  scaled error {f(b['nmse_before'])} → {f(b['nmse_after'])} (lower is better)")
        for x in b["parts"]:
            r2 = lambda v: "–" if v is None else f"{v:.2f}"   # noqa: E731
            out.append(f"           {x['ref']}: R² {r2(x['r2_before'])} → {r2(x['r2_after'])}")
    if b.get("margins"):
        out.append(f"  BENEFIT  {b['margins']}")
    for c in e["conflicts"]:
        out.append(f"  CONFLICT {c['id']}: {c['why']}")
    if e.get("not_simulated"):
        out.append(f"  EFFECT   not simulated: {e['not_simulated']}")
    d = e["diff"]
    out.append("  DIFF" + (f"     (cannot be made: {d['error']})" if "error" in d else ""))
    out += ["    " + x for x in (d.get("unified") or "").rstrip("\n").split("\n") if "error" not in d]
    return out
