"""The improvers the benchmark runs: a block's job, proposing changes to the model with their evidence (SPEC §12e).

- **stand-in** (``StandIn``, a program: free, deterministic, seconds): it knows nothing of the truth or of what
  was planted. Each round it tries a fixed menu of changes a modeller would try, on the record so far: every
  parameter retuned; each term of an equation dropped, or its sign flipped; a drain, an inflow or a transfer added
  to a stock; a third-order or first-order delay put on a flow; a stock put back where a series the model does not
  read was measured. Each is tuned (its new numbers, by a search on the replay's scaled error) and scored; the best
  two that lower the error by ``GAIN`` or more, not on the same part, are proposed with the statistic that says so
  and the rule they follow. What the judge failed, or ergostat refused, is not proposed again.
- **calibrator** (``Calibrator``, a program): what the examples' stand-ins do, the calibration's estimates proposed
  for the judge; parameters only.
- **AI** (``AI``, ``claude -p``): the model, its fit, its findings and the series it does not read, and how to
  propose; it answers with propose lines. Run only on demand (``ergostat bench improve --improver ai``)."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time

from ..numbers import observe as ob
from ..numbers import simulate as sim
from ..numbers import version as ver
from ..numbers import yamledit as ye
from ..spec import equation as eq
from ..spec.ir import Spec
from . import form as fm
from . import truth as tt

GAIN = 0.05            # the least fall in scaled error (a share) worth proposing
MOST = 2               # proposals a round
PARSIMONY = 0.01       # each new parameter must buy this much more


def _nmse(spec: Spec, data: ob.Data, params: dict | None = None) -> float:
    """The replay's scaled error, every measured stock counted (never the fit's total, which leaves out a stock
    slower than the record: a change that slows one would look better)."""
    from ..numbers.judge import per_stock
    try:
        run = sim.replay(spec, data, sim.plan(spec, params or {}))
    except Exception:
        return math.inf
    if not run.valid:
        return math.inf
    per = per_stock(spec, data, run)
    want = [r for r in data.values if r.startswith("stock.") and data.first(r) is not None]
    if not per or any(r not in per for r in want if r[6:] in spec.stocks):
        return math.inf
    v = sum(per.values()) / len(per)
    return v if math.isfinite(v) else math.inf


def tune(spec: Spec, data: ob.Data, names: list[str], rounds: int = 2) -> tuple[dict[str, float], float]:
    """The values of ``names`` that lower the replay's scaled error, one at a time: a factor of two each way, then
    narrowed (each value's sign kept)."""
    vals = {n: spec.parameters[n].value or 1.0 for n in names}
    best = _nmse(spec, data, vals)
    w = data.grid.width / 3600.0                       # a bucket, in hours: no time shorter, no rate faster, is tried

    def sane(n, v):
        u = spec.parameters[n].unit
        return not ((u == "h" and abs(v) < w) or (u == "1/h" and abs(v) > 1 / w))
    for _ in range(rounds):
        for n in names:
            step = 4.0
            while step > 1.04:
                moved = False
                for f in (step, 1 / step):
                    trial = {**vals, n: vals[n] * f}
                    if not sane(n, trial[n]):
                        continue
                    e = _nmse(spec, data, trial)
                    if e < best - 1e-12:
                        best, vals, moved = e, trial, True
                        break
                if not moved:
                    step = math.sqrt(step)
    return vals, best


class StandIn:
    name = "stand-in"

    def __init__(self):
        self.tried: set[str] = set()          # what it proposed before: never again
        self.cost = {"usd": 0.0, "tokens": 0, "calls": 0}

    # ---- the menu

    def moves(self, m: dict, orphans: list[str]) -> list[tuple[str, str, dict, list[str]]]:
        """``(title, rule, model after, parameters to tune)`` for every change on the menu."""
        out = []
        for p in m["parameters"]:
            out.append((f"retune {p}", "parameter-assessment", fm.copy_of(m), [p]))
        stocks = list(m["stocks"])
        for fname, f in m["flows"].items():
            if not f.get("equation"):
                continue
            ts = fm.terms(f["equation"])
            own = sorted(fm.params_of(eq.parse(f["equation"])))
            for i in range(len(ts)) if len(ts) > 1 else []:
                a = fm.copy_of(m)
                t2 = list(ts)
                t2[i] = (-t2[i][0], t2[i][1])
                a["flows"][fname]["equation"] = fm.of_terms(t2)
                _flip_causes(a["flows"][fname], ts, i)
                out.append((f"{fname}: the sign of {eq.text(ts[i][1])} flipped", "structure-assessment", a, own))
                b = fm.copy_of(m)
                b["flows"][fname]["equation"] = fm.of_terms([x for j, x in enumerate(ts) if j != i])
                fm.tidy_causes(b["flows"][fname])
                fm.drop_unused(b)
                out.append((f"{fname}: without {eq.text(ts[i][1])}", "simplest-structure", b,
                            [x for x in own if x in b["parameters"]]))
            tree = eq.parse(f["equation"])
            if not (tree[0] == "fn" and tree[1].startswith(("DELAY", "SMOOTH"))) and (f.get("to") or not f.get("from")):
                for fn in ("DELAY3", "DELAY1"):
                    a = fm.copy_of(m)
                    tau = fm.free_name(a, f"{fname}-delay")
                    a["parameters"][tau] = {"value": 1.0, "unit": "h", "estimate": True}
                    if f.get("from") and f.get("to"):         # between two stocks: it leaves at once, arrives delayed
                        arrives = fm.free_name(a, f"{f['to']}-arrives")
                        a["flows"][fname]["to"] = None
                        a["flows"][arrives] = {"from": None, "to": f["to"], "driven_by": [f"+flow.{fname}"],
                                               "equation": f"{fn}(flow.{fname}, {tau})"}
                    else:
                        a["flows"][fname]["equation"] = f"{fn}({f['equation']}, {tau})"
                    out.append((f"{fname} through a {'third' if fn == 'DELAY3' else 'first'}-order delay", "missing-delay",
                                a, [tau]))
        for s in stocks:
            unit = m["stocks"][s].get("unit") or "units"
            a = fm.copy_of(m)
            k = fm.free_name(a, f"{s}-drain-rate")
            a["parameters"][k] = {"value": 1.0, "unit": "1/h", "estimate": True}
            a["flows"][fm.free_name(a, f"{s}-drain")] = {"from": s, "to": None, "driven_by": [f"+stock.{s}"],
                                                          "equation": f"{k} * stock.{s}"}
            out.append((f"{s} drains", "stock-without-outflow", a, [k]))
            a = fm.copy_of(m)
            k = fm.free_name(a, f"{s}-inflow-rate")
            a["parameters"][k] = {"value": 1.0, "unit": f"{unit}/h", "estimate": True}
            a["flows"][fm.free_name(a, f"{s}-inflow")] = {"from": None, "to": s, "driven_by": [], "equation": k}
            out.append((f"{s} fills at a rate", "boundary", a, [k]))
            for t in stocks:
                if t == s or any(f["from"] == s and f["to"] == t for f in m["flows"].values()):
                    continue
                a = fm.copy_of(m)
                k = fm.free_name(a, f"{s}-to-{t}-rate")
                a["parameters"][k] = {"value": 1.0, "unit": "1/h", "estimate": True}
                a["flows"][fm.free_name(a, f"{s}-to-{t}")] = {"from": s, "to": t, "driven_by": [f"+stock.{s}"],
                                                               "equation": f"{k} * stock.{s}"}
                out.append((f"{s} moves to {t}", "structure-assessment", a, [k]))
        for name in orphans:
            for fname, f in m["flows"].items():
                if not f.get("to") or f["to"] == name:
                    continue
                a = fm.copy_of(m)
                was_to = f["to"]
                a["stocks"][name] = {"unit": m["stocks"][was_to].get("unit"), "sensor": True}
                a["flows"][fname]["to"] = name
                k = fm.free_name(a, f"{name}-out-rate")
                a["parameters"][k] = {"value": 1.0, "unit": "1/h", "estimate": True}
                a["flows"][fm.free_name(a, f"{name}-to-{was_to}")] = {"from": name, "to": was_to,
                                                                       "driven_by": [f"+stock.{name}"],
                                                                       "equation": f"{k} * stock.{name}"}
                out.append((f"{name}, measured, between {fname} and {was_to}", "structure-assessment", a, [k]))
        return out

    # ---- a round

    def propose(self, p, loop, at: float, data: ob.Data) -> list[dict]:
        t0 = time.perf_counter()
        spec = p.model.spec
        text = p.model.path.read_text(encoding="utf-8")
        m = fm.of_spec(spec)
        base = _nmse(spec, data)
        if not math.isfinite(base) or base <= 0:
            return []
        v = ver.version(spec)
        for x in loop.changes().values():                  # what was failed or refused on this version: not again
            if x["state"] in ("failed", "rejected", "refused") and x.get("made_by") == self.name:
                self.tried.add(f"{x.get('version')}:{x.get('title')}")
        read = {s.series for kind in (spec.stocks, spec.flows, spec.auxiliaries) for x in kind.values() for s in x.sensors.values()}
        orphans = sorted({row["series"].split("/", 1)[1].split(".")[0] for row in p.measurements.series()
                          if row["series"].startswith("sensor/") and row["series"] not in read} - set(spec.stocks)
                         - set(spec.flows) - set(spec.auxiliaries))
        scored = []
        for title, rule, after, names in self.moves(m, orphans):
            if f"{v}:{title}" in self.tried:
                continue
            try:
                sp = tt.spec_of(fm.render(after))
            except ValueError:
                continue
            d = ob.measured(p, data.grid, sp) if set(sp.stocks) != set(spec.stocks) else data
            names = [n for n in names if n in sp.parameters]
            vals, e = tune(sp, d, names)
            near = [n for n in _near(after, m) if n in sp.parameters and n not in names]
            if near and not title.startswith("retune"):          # a change to the structure moves its neighbours' numbers
                for n, val in vals.items():
                    after["parameters"][n]["value"] = val
                sp = tt.spec_of(fm.render(after))
                vals, e = tune(sp, d, names + near, rounds=1)
            new = len(set(after["parameters"]) - set(m["parameters"]))
            gain = (base - e) / base - PARSIMONY * new
            if gain >= GAIN:
                for n, val in vals.items():
                    after["parameters"][n]["value"] = float(ye.number(val))
                scored.append((gain, title, rule, after, e))
        scored.sort(key=lambda x: -x[0])
        out, touched = [], set()
        for gain, title, rule, after, e in scored:
            changed = _touched(m, after)
            if changed & touched:
                continue
            new_text = fm.render(after)
            hunks = fm.hunks(text, new_text)
            if not hunks:
                continue
            touched |= changed
            self.tried.add(f"{v}:{title}")
            worst = max(((r, s) for r, s in (_fit(spec, data).get("stocks") or {}).items() if s and s.get("r2") is not None),
                        key=lambda x: -(1 - x[1]["r2"]), default=None)
            reasons = [{"says": f"with it the replay's scaled error falls from {base:.3g} to {e:.3g} on the record so far",
                        "evidence": "fit:total.nmse"},
                       {"says": _rule_says(rule), "evidence": f"rule:{rule}"}]
            if worst:
                reasons.append({"says": f"the replay of {worst[0]} is the worst (R² {worst[1]['r2']:.2f})",
                                "evidence": f"fit:{worst[0]}.r2"})
            out.append({"kind": "parameter" if title.startswith("retune") else "structure", "parts": sorted(changed),
                        "title": title, "edit": {"files": [{"file": "ergostat.yaml", "hunks": hunks}]},
                        "reasons": reasons, "confidence": round(min(0.9, 0.3 + gain), 2)})
            if len(out) >= MOST:
                break
        self.cost["calls"] += 1
        self.cost["improver_seconds"] = round(self.cost.get("improver_seconds", 0.0) + time.perf_counter() - t0, 1)
        return out


def _fit(spec: Spec, data: ob.Data) -> dict:
    from ..numbers import trial as tr
    try:
        return tr.fit_of(spec, data)[1]
    except Exception:
        return {}


def _flip_causes(f: dict, ts, i: int) -> None:
    others = set().union(*(fm.refs_of(t) for j, (_, t) in enumerate(ts) if j != i))
    mine = fm.refs_of(ts[i][1]) - others
    new = []
    for c in f.get("driven_by") or []:
        s = c["cause"] if isinstance(c, dict) else c
        if s.lstrip("+-") in mine and s[:1] in "+-":
            s = ("-" if s[0] == "+" else "+") + s[1:]
        new.append({**c, "cause": s} if isinstance(c, dict) else s)
    f["driven_by"] = new


def _near(after: dict, before: dict) -> list[str]:
    """The parameters of the flows at the stocks a change touches: what it may move besides its own."""
    stocks = {r.split(".", 1)[1] for r in _touched(before, after) if r.startswith("stock.")}
    for r in _touched(before, after):
        if r.startswith("flow."):
            f = after["flows"].get(r[5:]) or before["flows"].get(r[5:]) or {}
            stocks |= {f.get("from"), f.get("to")} - {None}
    out: list[str] = []
    for f in after["flows"].values():
        if f.get("equation") and ({f.get("from"), f.get("to")} & stocks):
            out += [n for n in sorted(fm.params_of(eq.parse(f["equation"]))) if n not in out]
    return out


def _touched(a: dict, b: dict) -> set[str]:
    out = set()
    for sec, k in (("stocks", "stock"), ("flows", "flow"), ("parameters", "parameter")):
        for n in set(a[sec]) | set(b[sec]):
            if a[sec].get(n) != b[sec].get(n):
                out.add(f"{k}.{n}")
    return out


def _rule_says(rule: str) -> str:
    return {"parameter-assessment": "a parameter is measurable: the record says its value",
            "structure-assessment": "the model's structure should be the system's",
            "simplest-structure": "what explains nothing goes",
            "missing-delay": "a cause far from its effect goes through a delay",
            "stock-without-outflow": "what fills a stock leaves it somehow",
            "boundary": "what comes from outside the model is said"}.get(rule, rule)


# ---- the AI

PROMPT = """You are reviewing a system dynamics model written for ergostat, as a senior modeller would. The model
does not reproduce the record well. Find what is wrong with its structure or its numbers, and propose at most
{most} changes that fix it. You see only the record so far; each change you propose is replayed on the record that
comes after it, and kept only when it fits better there than the record's noise can explain.

The model (ergostat.yaml):
```yaml
{model}
```

How it fits the record so far (the replay's scaled error, lower is better; per stock R², and Theil's bias um,
variance us, covariance uc):
{fit}

What `ergostat check` finds:
{findings}

Series in the record that the model does not read: {orphans}
{history}
Answer with JSON lines only, one per change, nothing else:
{{"propose": {{"kind": "parameter|equation|structure", "parts": ["flow.NAME"], "title": "a few words",
  "edit": {{"file": "ergostat.yaml", "replace": "the lines exactly as written now, with their indentation", "with": "what they become"}},
  "reasons": [{{"says": "why", "evidence": "fit:total.nmse"}}, {{"says": "the rule it follows", "evidence": "rule:NAME"}}],
  "confidence": 0.6}}}}

Evidence ergostat can check: fit:total.nmse, fit:stock.NAME.r2 (or .um .us .uc .mape), finding:CODE@PART (from the
findings above), rule:NAME (one of {rules}). A reason without checkable evidence is refused. A new parameter is
written under parameters: with value, unit and estimate: true. Equations use stock.NAME, flow.NAME, auxiliary.NAME,
parameter names, + - * / ^, MIN, MAX, ABS, EXP, LN, SQRT, ZIDZ, XIDZ, DELAY1(x, time), DELAY3(x, time), SMOOTH, SMOOTH3;
times in hours. A flow's driven-by lists the parts its equation names, with their signs."""


class AI:
    name = "ai"

    def __init__(self, model: str = "sonnet", timeout: float = 600.0):
        self.model, self.timeout = model, timeout
        self.cost = {"usd": 0.0, "tokens": 0, "tokens_in": 0, "tokens_out": 0, "calls": 0, "model": model, "failed": 0}
        self.history: list[str] = []

    def prompt(self, p, loop, data: ob.Data) -> str:
        from ..numbers import improve as im
        from ..spec import read
        spec = p.model.spec
        fit = _fit(spec, data)
        lines = [f"- total: {((fit.get('total') or {}).get('nmse')) if fit.get('total') else 'not valid'}"]
        for r, s in (fit.get("stocks") or {}).items():
            if s:
                lines.append(f"- {r}: " + ", ".join(f"{k} {s[k]:.3g}" for k in ("r2", "mape", "um", "us", "uc") if s.get(k) is not None))
        _, problems = read(p.model.path)
        fs = [f"- {x.code}@{x.about}: {x.message}" if x.about else f"- {x.code}: {x.message}" for x in problems if x.level != "error"]
        read_ = {s.series for kind in (spec.stocks, spec.flows, spec.auxiliaries) for x in kind.values() for s in x.sensors.values()}
        orphans = sorted(r["series"] for r in p.measurements.series() if r["series"] not in read_ and r["series"].startswith("sensor/"))
        hist = ("\nWhat became of your earlier proposals:\n" + "\n".join(self.history[-8:]) + "\n") if self.history else ""
        return PROMPT.format(most=2, model=p.model.path.read_text(encoding="utf-8").rstrip(), fit="\n".join(lines),
                             findings="\n".join(fs) or "- nothing", orphans=", ".join(orphans) or "none", history=hist,
                             rules=", ".join(im.RULES))

    def propose(self, p, loop, at: float, data: ob.Data) -> list[dict]:
        for x in loop.changes().values():
            if x.get("made_by") == self.name and x["state"] in ("failed", "rejected", "refused", "accepted", "superseded",
                                                                 "sent-back"):
                line = f"- {x.get('title')}: {x['state']}" + (f" ({(x.get('verdict') or {}).get('why') or x.get('why') or ''})")
                if line not in self.history:
                    self.history.append(line)
        text = self.prompt(p, loop, data)
        cmd = [os.environ.get("ERGOSTAT_AI") or "claude", "-p", "--model", self.model, "--output-format", "json",
               "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"]
        t0 = time.perf_counter()
        try:
            got = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=self.timeout)
            out = json.loads(got.stdout)
        except (subprocess.TimeoutExpired, ValueError, OSError):
            self.cost["failed"] += 1
            return []
        self.cost["calls"] += 1
        self.cost["improver_seconds"] = round(self.cost.get("improver_seconds", 0.0) + time.perf_counter() - t0, 1)
        self.cost["usd"] += float(out.get("total_cost_usd") or 0.0)
        u = out.get("usage") or {}
        tin = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
        tout = int(u.get("output_tokens") or 0)
        self.cost["tokens_in"] += tin
        self.cost["tokens_out"] += tout
        self.cost["tokens"] += tin + tout
        props = []
        for line in str(out.get("result") or "").splitlines():
            line = line.strip().strip("`")
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("propose"), dict):
                props.append(obj["propose"])
        return props[:2]


class Calibrator:
    """What the examples' stand-in improvers do (``examples/image-squeeze/bin/standin_improver.py``): propose the
    calibration's own estimates (each part alone, the last fifth of the record held out), the ones ergostat would
    not propose itself too, and let the judge decide on the record after them. A parameter's value only: it never
    changes the structure."""

    name = "calibrator"

    def __init__(self):
        self.tried: set[tuple[str, str]] = set()
        self.cost = {"usd": 0.0, "tokens": 0, "calls": 0}

    def propose(self, p, loop, at: float, data: ob.Data) -> list[dict]:
        from ..numbers import estimate as es
        from . import clock
        t0 = time.perf_counter()
        with clock.at(at):
            got = es.estimate(p, {"at": at})
        spec = p.model.spec
        text = p.model.path.read_text(encoding="utf-8")
        v = ver.version(spec)
        out = []
        for e in sorted(got.values(), key=lambda e: str(e.get("parameter"))):
            n, val, was = e.get("parameter"), e.get("value"), e.get("declared")
            if n not in spec.parameters or val is None or was is None or e.get("at_bound") or abs(val - was) <= 0.02 * abs(was):
                continue
            if (v, n) in self.tried:
                continue
            m = fm.of_spec(spec)
            m["parameters"][n]["value"] = float(ye.number(val))
            hunks = fm.hunks(text, fm.render(m))
            if not hunks:
                continue
            self.tried.add((v, n))
            out.append({"kind": "parameter", "parts": [f"parameter.{n}"], "title": f"{n}: the calibration's estimate",
                        "edit": {"files": [{"file": "ergostat.yaml", "hunks": hunks}]}, "confidence": 0.3,
                        "reasons": [{"says": f"the record's estimate of {n} is {ye.number(val)}, not {ye.number(was)}",
                                     "evidence": "fit:total.nmse"},
                                    {"says": "a parameter is measurable: the record says its value",
                                     "evidence": "rule:parameter-assessment"}]})
            if len(out) >= MOST:
                break
        self.cost["calls"] += 1
        self.cost["improver_seconds"] = round(self.cost.get("improver_seconds", 0.0) + time.perf_counter() - t0, 1)
        return out


def make(name: str, model: str = "sonnet"):
    if name in ("standin", "stand-in"):
        return StandIn()
    if name == "calibrator":
        return Calibrator()
    if name == "ai":
        return AI(model)
    raise KeyError(f"no improver {name}: standin, calibrator, ai")
