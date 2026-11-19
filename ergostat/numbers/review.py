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
from . import gate as gt
from . import improve as im
from . import leverage as lv
from . import observe as ob
from . import predict as pd
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
    pr.supersede(p, spec)                             # made against another version: carried, or let go if its subject went
    props = pr.stored(p)
    mine = {x["id"] for x in found}
    for k in [k for k, x in props.items() if x.get("kind") == "structure" and x["status"] == "pending" and
              not pr.candidate(x) and k not in mine]:
        del props[k]                                  # superseded: no longer found
    fresh = []
    for x in found:
        x["made_by"] = "ergostat"
        if x["id"] in props:                           # dismissed (or accepted, or pending) already: not made again
            continue
        again = None
        try:
            after_spec = tr.spec_after(p, tr.edits_of(x))
            data_a = ob.measured(p, data.grid, after_spec)
            _, after = tr.fit_of(after_spec, data_a)
            again = im.refit(spec, after_spec, data_a)       # what it adds to estimate, fitted: the gate judges it so
        except tr.TrialError:
            after = None
        best = again["fit"] if again and gt.total(again["fit"]) is not None and \
            (gt.total(after) is None or gt.total(again["fit"]) < gt.total(after)) else after
        fresh.append({**x, "fit_before": base, "fit_after": after or {"total": None, "stocks": {}, "equations": {}},
                      "refit": again, "gate_fit": best, "span": data.grid.until - data.grid.since})
    pr.admit(p, spec, props, fresh, now, data.grid.until - data.grid.since)   # held back, refused at the gate, or pending
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
    if k == "redesign":
        return f"A redesign of {'the whole model' if (x.get('system') or 'model') == 'model' else x['system']}, " \
               f"{len((x.get('redesign') or {}).get('edits') or [])} edits judged together, proposed by {x.get('made_by')}"
    if x.get("said_kind"):                          # made by a block (a propose line), not by ergostat's own finders
        n = len(x.get("parameters") or {})
        words = {"parameter": "A parameter's value" if n <= 1 else f"{n} parameters' values", "equation": "An equation",
                 "structure": "A change to the structure"}.get(k, "A change")
        return f"{words}, proposed by {x['made_by']}"
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
    if x.get("said_kind"):
        c = x.get("confidence")
        r = (x.get("refit") or {}).get("values")
        return {"method": x.get("method"), "span": span, "n": None,
                "confidence": "; ".join(b for b in (f"{x['made_by']} is {c:.0%} sure" if c is not None else None,
                                                     ("refitted, " + ", ".join(f"{n} = {ye.number(v)}" for n, v in r.items()))
                                                     if r else None) if b) or None}
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
    if k == "redesign":
        return x.get("summary") or x.get("reason") or x.get("title") or ""
    if x.get("said_kind"):
        return "; ".join(f"{r['says']} ({'; '.join(r.get('verified') or r.get('evidence') or [])})" for r in x.get("reasons") or []) + "."
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
    g = x.get("gate") or {}
    whole = g.get("whole") or {"before": b.get("nmse"), "after": a.get("nmse")}
    out["said"] = g.get("said") or gt.summary({"whole": whole, "local": None})   # both numbers, and which way they went
    out["better"] = None if whole.get("before") is None or whole.get("after") is None else \
        whole["after"] < whole["before"] - gt.TRIFLE and not (g.get("local") and g["local"]["after"] > g["local"]["before"] + gt.TRIFLE)
    out["local"] = g.get("local")
    if x.get("kind") == "tuning":
        out["margins"] = x.get("reason", "").split(". ", 1)[1] if ". " in x.get("reason", "") else None
    return out


def diff_of(x: dict, root: Path | None = None) -> dict:
    """Exactly what Accept writes: each file's text now and after, as a unified diff, and its hash."""
    try:
        edits = tr.edits_of(x)
        new = ye.apply_together(edits)
    except (tr.TrialError, ye.EditError) as e:
        return {"error": str(e)}
    parts = []
    for f, text in sorted(new.items()):
        old = Path(f).read_text(encoding="utf-8")
        parts.append(ye.unified(old, text, _rel(f, root)))
    text = "".join(parts)
    return {"unified": text, "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "files": [{"file": _rel(f, root), "lines": sorted({h.line for e in edits if e.file == f for h in e.hunks})}
                      for f in sorted(new)]}


def _rel(f: str, root: Path | None = None) -> str:
    """A file as the repository names it (from the model's folder), else its name."""
    try:
        return str(Path(f).resolve().relative_to((root or Path.cwd()).resolve()))
    except ValueError:
        return Path(f).name


def entry(x: dict, spec: Spec, others: list[dict] | None = None, root: Path | None = None) -> dict:
    parts = list(dict.fromkeys([*(x.get("parts") or []), *(x.get("touched") or [])]))
    if x.get("kind") in ("process", "tuning"):
        g = spec.goals.get(x.get("goal") or "")
        parts = [f"goal.{x['goal']}"] + ([f"{g.of.kind}.{g.of.name}"] if g else []) + \
            ([f"block.{x['block']}"] if x.get("block") else [])
    sel = selectable(spec, parts)
    d = diff_of(x, root)
    clash = [{"id": y["id"], "why": w} for y in (others or []) if (w := tr.conflicts(x, y))]
    simulable = x.get("kind") in ("parameter", "equation", "structure", "redesign") and "error" not in d
    return {"id": x["id"], "source": "control" if x.get("kind") in ("process", "tuning") else "numbers",
            "kind": x.get("kind"), "code": x.get("code"), "what": _what(x), "title": x.get("title"),
            "where": {"parts": parts, "select": sel, "words": [_words(r) for r in parts], "systems": _systems(spec, sel),
                      "new": x.get("new_parts") or [], "gone": x.get("gone_parts") or [], "files": d.get("files") or []},
            "why": _why(x, spec), "how": _how(x, spec), "benefit": _benefit(x), "reason": x.get("reason"),
            "diff": d, "conflicts": clash, "simulable": simulable,
            "not_simulated": None if simulable else ("the replay takes what a controller sets as measured, so a loop's "
                                                     "process or gain changes no replay; its effect is the step response "
                                                     "and margins on the loop's panel" if x.get("kind") in ("process", "tuning")
                                                     else d.get("error")),
            "created": x.get("created"), "status": x.get("status", "pending"), **_by(x),
            **({"redesign": redesign_view(x)} if x.get("kind") == "redesign" else {})}


def redesign_view(x: dict) -> dict:
    """A change set as its review section shows it: the system, what it does and why, each edit with its why, the
    parts it adds, takes away, renames and changes, the scorecard (as the judge last worked it out), and its cost."""
    r = x.get("redesign") or {}
    card = x.get("scorecard") or {}
    return {"system": x.get("system") or "model", "summary": x.get("summary"), "edits": r.get("edits") or [],
            "parts": r.get("parts") or card.get("parts") or {}, "scorecard": card, "cost": r.get("cost"),
            "rounds": r.get("rounds")}


def _by(x: dict) -> dict:
    """Who made it (a block by its propose line, ergostat's own finders, or the owner's what-if, SPEC §12e), its item,
    its state, and, when a block made it, its rung, its reasons with the evidence each was checked against and how sure
    it said it is; what ergostat found it answers; and the judge's verdict."""
    v = dict(x.get("verdict") or {})
    if v:
        v["windows"] = len(v.get("windows") or [])
    elif x.get("state") == "testing":
        v = {"verdict": "testing", "why": "replayed on the record after it was made, until its hold-out is long enough"}
    block = bool(x.get("made_by") and x["made_by"] not in ("ergostat", "owner"))
    return {"made_by": x.get("made_by") or "ergostat", "made_by_rung": x.get("made_by_rung"), "by_block": block,
            "item": f"ergostat.model-change/{x['id']}", "state": x.get("state"),
            "reasons": x.get("reasons") or [] if block else [], "confidence": x.get("confidence"),
            "findings": x.get("findings") or {}, "verdict": v or None}


def _systems(spec: Spec, parts: list[str]) -> list[str]:
    """The systems to open so the parts are drawn themselves, not inside a closed system: each holding one,
    and the systems holding those."""
    from ..correspond import system_of
    out: list[str] = []
    for r in parts:
        s = system_of(spec, r)
        if s:
            out += [x for x in spec.chain(s) if x not in out]
    return out


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
    order = {"redesign": -1, "parameter": 0, "equation": 1, "structure": 2, "process": 3, "tuning": 4}
    xs.sort(key=lambda x: (order.get(x.get("kind"), 9), x.get("created") or 0))
    root = p.model.path.parent if getattr(p.model, "path", None) else None
    return [entry(x, spec, xs, root) for x in xs]


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
    out: dict = {"taken": [x["id"] for x in taken], "left": left, "since": grid.since, "until": grid.until}
    if not taken:
        return {**out, "charts": [], "operational": [], "leverage": []}
    try:
        after = tr.spec_after(p, edits)
    except tr.TrialError as e:
        return {**out, "error": str(e), "charts": [], "operational": [], "leverage": []}
    f = forecast(p, spec, after, taken, at)
    data, data_a, run, run_a, horizon = f["data"], f["data_a"], f["run"], f["run_a"], f["horizon"]
    proj_b, proj_a, loops = f["before"], f["after"], f["loops"]
    ref = ob.reference(p, at)                          # the fit on the page's own grid (the Fit table's), as of now
    _, fit_b = tr.fit_of(spec, ob.measured(p, ref))
    _, fit_a = tr.fit_of(after, ob.measured(p, ref, after))
    refs = _charted(after, taken, 4 * most) or _charted(spec, taken, 4 * most)
    charts, undrawn = [], []
    for r in refs:
        kind, _, name = r.partition(".")
        x = after.measured(kind).get(name) or spec.measured(kind).get(name)
        c = {"ref": r, "name": name, "kind": kind, "unit": getattr(x, "unit", "") or "",
             "per": kind == "flow", "new": r in {n for t in taken for n in (t.get("new_parts") or [])},
             "gone": name not in after.measured(kind),
             "measured": _round(data.values.get(r) or data_a.values.get(r)),
             "before": _round(run.values.get(r)) if r in run.how else None,
             "after": _round(run_a.values.get(r)) if r in run_a.how else None,
             "proj_before": _round(proj_b.values.get(r)) if proj_b.values.get(r) else None,
             "proj_after": _round(proj_a.values.get(r)) if proj_a and proj_a.values.get(r) else None}
        if not any(v is not None for k in ("measured", "before", "after") for v in (c[k] or [])):
            undrawn.append(f"{_words(r)}{' (new)' if c['new'] else ''}: no record and nothing to start a replay from")
            continue
        if c["after"] == c["before"] and c["proj_after"] == c["proj_before"]:
            c["same"] = True                               # the change leaves it as it was: one line, not two
            c["after"] = c["proj_after"] = None
        charts.append(c)
    charts = sorted(charts, key=lambda c: c.get("same", False))[:most]
    flows = [r.split(".", 1)[1] for t in taken for r in (t.get("touched") or []) + (t.get("parts") or [])
             if r.startswith("flow.") and r.split(".", 1)[1] in after.flows]
    lev = []
    if run_a.valid:
        try:
            lev = _leverage(p, after, data_a, run_a, horizon, list(dict.fromkeys(flows))[:6], base_leverage)
        except Exception:                                     # leverage is a help to reading, never a reason to fail
            lev = []
    return {**out, "times": [round(t, 3) for t in grid.times()], "ptimes": [round(t, 3) for t in proj_b.times],
            "horizon": horizon, "loops": loops, "charts": charts, "undrawn": undrawn,
            "fit_before": fit_b, "fit_after": fit_a, "valid": run_a.valid, "invalid": run_a.invalid,
            "operational": operational(after, refs, proj_b, proj_a, grid.until, horizon) if proj_a else [],
            "predicts": f["predicts"],
            "leverage": lev}


def forecast(p, spec: Spec, after: Spec, xs: list[dict], at: float | None = None) -> dict:
    """The model's forecast as it is and with the change(s) applied in memory: the replays on the reference window, and
    the projections over the horizon with the loops running where there are controllers; and what it predicts of the
    stocks they touch, in a sentence (``predict.stated``). The one function both the review entry's strip and the
    prediction recorded on acceptance come from."""
    grid = ob.reference(p, at, CHART_POINTS)
    data, data_a = ob.measured(p, grid), ob.measured(p, grid, after)
    run, run_a = sim.replay(spec, data, sim.plan(spec)), sim.replay(after, data_a, sim.plan(after))
    from .simulate import horizon_of
    horizon = horizon_of(run, grid.until - grid.since)
    points = max(2, round(CHART_POINTS * horizon / max(grid.until - grid.since, 1.0)))
    b, a, loops = _projections(p, spec, after, data, data_a, run, run_a, horizon, points)
    refs = _charted(after, xs, 4 * CHARTS) or _charted(spec, xs, 4 * CHARTS)
    return {"data": data, "data_a": data_a, "run": run, "run_a": run_a, "horizon": horizon, "before": b, "after": a,
            "loops": loops, "predicts": pd.stated(after, refs, b, a, grid.until, horizon, loops) if a else None}


def _projections(p, spec: Spec, after: Spec, data, data_a, run, run_a, horizon: float, points: int):
    """The model's projection as it is and with the change: with the loops running where the model has controllers
    (closedloop.projection), else held. (before, after or None, "closed" or "held")"""
    from . import closedloop as cl
    loops = "closed" if cl.has_controllers(spec) else "held"
    b = cl.projection(p, spec, data, run, horizon, sim.plan(spec), points, loops)["projection"]
    a = cl.projection(p, after, data_a, run_a, horizon, sim.plan(after), points, loops)["projection"] if run_a.valid else None
    return b, a, loops


def base_leverage(p, spec: Spec, at: float | None = None) -> dict | None:
    if not spec.goals:
        return None
    grid = ob.reference(p, at, CHART_POINTS)
    data = ob.measured(p, grid)
    run = sim.replay(spec, data, sim.plan(spec))
    if not run.valid:
        return None
    from .simulate import horizon_of
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
    if e.get("redesign"):
        from . import scorecard as sc
        rd_ = e["redesign"]
        out.append(f"  EDITS    {len(rd_['edits'])}, made in order:")
        out += [f"           {i + 1}. {x['said']}" + (f": {x['why']}" if x.get("why") else "") for i, x in enumerate(rd_["edits"])]
        if rd_.get("scorecard"):
            out += ["  " + x for x in sc.lines(rd_["scorecard"])]
    d = e["diff"]
    out.append("  DIFF" + (f"     (cannot be made: {d['error']})" if "error" in d else ""))
    out += ["    " + x for x in (d.get("unified") or "").rstrip("\n").split("\n") if "error" not in d]
    return out
