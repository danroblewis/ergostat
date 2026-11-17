"""Structural proposals: a change to what the model says moves what, each with its YAML edit, where it is,
why, how it was found and, when the model it leaves can be replayed, its effect. They come from what
ergostat already finds:

- **check's findings with a concrete fix** (SPEC §12): a rate that follows a rate gets a stock between,
  with its two flows; a stock nothing drains gets an outflow to a cloud (sized by Little's law from the
  record) or, when nothing leaves it, is marked cumulative; a flow driven by another in other units gets
  the auxiliary that converts them; a link whose sign its equation contradicts gets the equation's sign
  (or, where the sign changes across the range, none); a one-way flow whose equation runs backwards under
  an extreme condition gets a guard (``MAX(0, …)``), and a division that faults gets ``ZIDZ``; an
  auxiliary with no causes is marked exogenous;
- **the estimators**: a coefficient whose estimate is indistinguishable from 0 with a narrow interval
  (its term moves its part by little either way) is taken out of its equation with its link; a declared
  sign the regression of a flow on its causes contradicts is flipped;
- **simplification, by SD Lab's tested rules** (its SPEC §4.8): a measured flow that moved essentially
  nothing over the record, or an equation-only flow whose removal does not worsen the replay, is
  removed; two flows between the same two stocks are merged; a stock nearly always empty with one flow
  in from a stock and one out to a stock is a pass-through (the flows joined, the stock removed); a stock
  that never changes, is nearly always empty, moves exactly like another (a twin) or that nothing touches
  is removed. ergostat has no ``hide:``, so where SD Lab hides a stock this proposes its removal, and the
  edit says what else goes with it. A stock a goal holds, and what a goal or a block names, is left alone.

Not yet: **missing stocks, flows or delays, and replacing a part**, found from the pattern in what the
model fails to explain (the residuals). That is the residual-pattern structure finder (``from_residuals``
below), the next piece of work; until it is built it proposes nothing, and the Fit page says so.

Each candidate's edit is applied in memory and the model compiled from it (``trial.py``): one that would
leave an error is not proposed, and is listed with why."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from ..spec import equation as eq
from ..spec.findings import base_unit, unit_of
from ..spec.ir import Ref, Spec
from . import observe as ob
from . import trial as tr
from . import yamledit as ye

EMPTY = 0.5             # SD Lab: a level under this is empty ...
NEARLY_ALWAYS = 0.95    # ... and a stock empty at this share of its readings is nearly always empty
STILL = 0.001           # a stock whose range is under this share of its mean never changes
TWIN = 0.999            # two stocks correlated past this, with a scale within 5%, move exactly alike
DEAD_MEAN, DEAD_PEAK = 0.001, 0.01   # a flow under these shares of the typical flow's rate moved nothing
NO_WORSE = 1.02         # a flow removed that leaves the scaled error within 2% explained nothing
MIN_READINGS = 20
NARROW = 0.1            # a term whose largest effect, its estimate ± 2σ, is under this share of its part's size

CAN = [
    ("a parameter's value", "calibrated on the replay (weighted least squares), or tried by you as a what-if"),
    ("an equation for a flow that has none", "least squares on its declared causes"),
    ("a loop's process, a controller's gain", "identification from the record or a step test; SIMC tuning"),
    ("a stock between a rate and the rate that follows it", "check: rate-driven-by-rate"),
    ("an outflow for a stock nothing drains, or cumulative: true", "check: stock-without-outflow, sized by Little's law"),
    ("an auxiliary converting one flow's units into another's", "check: units-mismatch"),
    ("a link's sign flipped or taken off", "check: equation-sign; a regression that contradicts the sign"),
    ("a guard: MAX(0, …), ZIDZ(a, b)", "check: extreme-conditions"),
    ("an auxiliary marked exogenous", "check: auxiliary-without-causes"),
    ("a term and its link removed", "an estimate indistinguishable from 0, with a narrow interval"),
    ("a flow removed, two flows merged, a pass-through stock joined, a stock removed", "SD Lab's simplify rules"),
]
CANNOT = [
    "a missing stock, flow or delay found from the residuals' pattern",
    "a part replaced by another form (a delay for a first-order drain, a lookup for a line)",
    "a cause named for an auxiliary (only marking it exogenous)",
    "a guard for a stock drained below empty (it needs a time to empty it in)",
]


def _id(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:8]


def _free(name: str, taken: set[str]) -> str:
    out, i = name, 2
    while out in taken:
        out, i = f"{name}-{i}", i + 1
    taken.add(out)
    return out


def _name_at(x, name: str) -> tuple[Path, int]:
    w = getattr(x, "defined", None) or x.where
    if w is None:
        raise ye.EditError(f"{name}: where it is written is not known")
    return Path(w.file), ye.name_line(Path(w.file), w.line, name)


def driven_text(items: list[tuple[str, int | None, bool]]) -> str:
    """A driven-by written out: each cause with its sign, ``instant: true`` where it is."""
    out = []
    for ref, sign, instant in items:
        s = ("+" if sign and sign > 0 else "-" if sign else "") + ref
        out.append(f"{{cause: {s}, instant: true}}" if instant else s)
    return out[0] if len(out) == 1 else "[" + ", ".join(out) + "]"


def causes_of(x) -> list[tuple[str, int | None, bool]]:
    return [(str(r), x.polarity.get(str(r)), str(r) in x.instant) for r in x.driven_by]


def _driven_edit(x, name: str, items) -> ye.Edit:
    path, at = _name_at(x, name)
    if not items:
        e = ye.remove_key(path, at, "driven-by")
        if e is None:
            raise ye.EditError(f"{name}: no driven-by to take away")
        return e
    return ye.set_key(path, at, "driven-by", driven_text(items))


class Ctx:
    def __init__(self, p, spec: Spec, data: ob.Data | None, estimates: dict | None = None):
        self.p, self.spec, self.data = p, spec, data
        self.estimates = estimates or {}
        self.taken = set(spec.stocks) | set(spec.flows) | set(spec.auxiliaries) | set(spec.parameters) | set(spec.goals) \
            | set(spec.blocks)
        self.out: list[dict] = []
        self.not_made: list[dict] = []
        self.named = self._named()

    def _named(self) -> set[str]:
        """What a goal or a block names: left alone by the simplifications."""
        out = {f"{g.of.kind}.{g.of.name}" for g in self.spec.goals.values()}
        for b in self.spec.blocks.values():
            out |= {f"{r.kind}.{r.name}" for r in b.reads()} | {f"{t.kind}.{t.name}" for t in b.targets()}
        return out

    def level(self, ref: str) -> list[float]:
        return [v for v in ((self.data.values.get(ref) if self.data else None) or []) if v is not None]

    def add(self, change: str, code: str, about: str, title: str, parts: list[str], why: str, method: str,
            edits: list[ye.Edit], touched: list[str] | None = None, finding: str | None = None, **more) -> None:
        try:
            joined = _joined(edits)
            spec = tr.spec_after(self.p, edits)
        except (ye.EditError, tr.TrialError) as e:
            self.not_made.append({"title": title, "why": str(e), "code": code})
            return
        if finding:                                   # the finding it answers is gone in the model it leaves
            from ..spec import findings as fd
            left = []
            fd.structure(spec, lambda c, m, w, a: left.append((c, a)))
            if (finding, about) in left:
                self.not_made.append({"title": title, "why": "the edit does not answer the finding", "code": code})
                return
        self.out.append({"id": _id("structure", code, about, joined["diff"]), "kind": "structure", "change": change,
                         "code": code, "target": about, "title": title, "parts": parts,
                         "touched": touched or [r for r in parts if r.split(".")[0] in ("stock", "flow", "auxiliary")],
                         "reason": why, "method": method, "edit": joined, "new_parts": sorted(_new_parts(self.spec, spec)),
                         "gone_parts": sorted(_new_parts(spec, self.spec)), **more})


def _new_parts(a: Spec, b: Spec) -> set[str]:
    return ({f"stock.{n}" for n in b.stocks} - {f"stock.{n}" for n in a.stocks}) | \
        ({f"flow.{n}" for n in b.flows} - {f"flow.{n}" for n in a.flows}) | \
        ({f"auxiliary.{n}" for n in b.auxiliaries} - {f"auxiliary.{n}" for n in a.auxiliaries})


def _joined(edits: list[ye.Edit]) -> dict:
    by: dict[str, list] = {}
    for e in edits:
        by.setdefault(e.file, []).append(e)
    files = [ye.merge(x) for x in by.values()]
    return {"files": [f.as_dict() for f in files], "diff": "\n".join(f.diff() for f in files)}


def _section_file(spec: Spec, near) -> Path:
    w = getattr(near, "defined", None) or getattr(near, "where", None)
    return Path(w.file) if w else Path(spec.path) if getattr(spec, "path", None) else None


# ---- check's findings, each made a change

def rate_driven_by_rate(c: Ctx, f, r: Ref) -> None:
    spec = c.spec
    src = spec.flows[r.name]
    s = _free(f"{r.name}-awaiting-{f.name}", c.taken)
    unit = base_unit(unit_of(spec, Ref("flow", r.name))) or ""
    unit = unit + "s" if unit and not unit.endswith("s") else unit
    path = _section_file(spec, f)
    stock = [f"  {s}:"] + ([f"    unit: {unit}"] if unit else []) + \
        [f"    description: what {r.name} moves, until {f.name} takes it on (proposed by ergostat)"]
    items = [(f"stock.{s}", 1, False) if x == str(r) else (x, sg, ins) for x, sg, ins in causes_of(f)]
    edits = [ye.add_entries(path, "stocks", [stock])]
    if src.target is None and f.source is None:        # the two flows meet at the new stock: r fills it, f drains it
        p1, a1 = _name_at(src, r.name)
        p2, a2 = _name_at(f, f.name)
        edits += [ye.set_key(p1, a1, "to", s), ye.set_key(p2, a2, "from", s), _driven_edit(f, f.name, items)]
        how = (f"{r.name} now fills {s} and {f.name} drains it, following what is there (driven-by +stock.{s}); "
               f"what {r.name} moves waits in {s} until {f.name} takes it on")
        flows = [f"flow.{r.name}", f"flow.{f.name}"]
    else:                                              # both already join stocks: the stock between gets its own two flows
        fin, fout = _free(f"{s}-in", c.taken), _free(f"{s}-out", c.taken)
        edits += [ye.add_entries(path, "flows", [
            [f"  {fin}:", f"    to: {s}", f"    driven-by: {{cause: +flow.{r.name}, instant: true}}   # as {r.name} moves"],
            [f"  {fout}:", f"    from: {s}", f"    driven-by: +stock.{s}"]]), _driven_edit(f, f.name, items)]
        how = (f"{s} is filled as {r.name} moves ({fin}) and drained as {f.name} takes it on ({fout}); {f.name} follows "
               f"what is in it (driven-by +stock.{s})")
        flows = [f"flow.{r.name}", f"flow.{f.name}", f"flow.{fin}", f"flow.{fout}"]
    c.add("a new stock with its two flows", "rate-driven-by-rate", f"flow.{f.name}",
          f"A stock {s} between {r.name} and {f.name}", [f"stock.{s}", *flows],
          f"{f.name} is driven by {r.name}, a rate following a rate: a connector acts at once, so the model says "
          f"{f.name} now depends on {r.name} now. A cause acting over time goes through a stock. {how}.",
          "a structural check (ergostat check: rate-driven-by-rate), on the model's structure alone", edits,
          touched=[f"flow.{f.name}"], finding="rate-driven-by-rate")


def stock_without_outflow(c: Ctx, st) -> None:
    spec = c.spec
    ref = f"stock.{st.name}"
    lv = c.level(ref)
    ins = [g for g in spec.flows_of(st.name) if g.target == st.name]
    span_h = (c.data.grid.until - c.data.grid.since) / 3600.0 if c.data else 0
    came = None
    if c.data and span_h > 0 and ins:
        w = c.data.grid.width / 3600.0
        moved = [sum(v for v in (c.data.values.get(f"flow.{g.name}") or []) if v is not None) * w for g in ins]
        came = sum(moved) if all(any(v is not None for v in (c.data.values.get(f"flow.{g.name}") or [])) for g in ins) else None
    if len(lv) >= MIN_READINGS and came is not None:
        left = came - (lv[-1] - lv[0])
        mean = sum(lv) / len(lv)
        if left < -0.05 * max(came, 1e-9):             # it rose by more than came in: an inflow is missing, not an outflow
            c.not_made.append({"title": f"An outflow from {st.name}", "code": "stock-without-outflow",
                               "why": f"it rose by {ye.number(lv[-1] - lv[0])} while its inflows brought {ye.number(came)}: an "
                                      f"inflow is missing or mismeasured, so what leaves cannot be told"})
            return
        if left <= 0.05 * max(came, 1e-9):             # nothing left it: a running total
            path, at = _name_at(st, st.name)
            c.add("a stock marked cumulative", "stock-without-outflow", ref, f"{st.name} marked cumulative: true", [ref],
                  f"flows fill {st.name} and nothing drains it, so in the model it can only grow. Over the record "
                  f"{ye.number(came)} came in and it rose by {ye.number(lv[-1] - lv[0])}: nothing left it, so it is a running "
                  f"total that never drains.",
                  "a structural check (stock-without-outflow), and a balance of the record: what came in against what the "
                  "stock rose by", [ye.set_key(path, at, "cumulative", "true")], finding="stock-without-outflow")
            return
        if mean > 0:
            rate = left / span_h
            hours = mean / rate
            out, tn = _free(f"{st.name}-leaving", c.taken), _free(f"time-in-{st.name}", c.taken)
            path = _section_file(spec, st)
            edits = [ye.add_entries(path, "flows", [[f"  {out}:", f"    from: {st.name}", f"    driven-by: +stock.{st.name}",
                                                     f"    equation: stock.{st.name} / {tn}"]]),
                     ye.add_entries(path, "parameters", [[f"  {tn}:", f"    value: {ye.duration(hours)}",
                                                          "    estimate: true          # proposed by ergostat, from Little's law; "
                                                          "refitted as the record grows"]])]
            c.add("a new outflow to a cloud", "stock-without-outflow", ref, f"An outflow {out} from {st.name}",
                  [ref, f"flow.{out}"],
                  f"flows fill {st.name} and nothing drains it, so in the model it can only grow; but over the record "
                  f"{ye.number(came)} came in and it rose by only {ye.number(lv[-1] - lv[0])}: {ye.number(left)} left it, by a "
                  f"way the model does not have. The outflow takes what is there over the time things stay ({ye.duration(hours)}).",
                  f"a structural check (stock-without-outflow); the time things stay by Little's law (its mean level "
                  f"{ye.number(mean)} over what left an hour, {ye.number(rate)})", edits,
                  touched=[ref], finding="stock-without-outflow")
            return
    c.not_made.append({"title": f"An outflow from {st.name}", "code": "stock-without-outflow",
                       "why": "the record does not say what leaves it (its level and every inflow measured are needed)"})


def units_mismatch(c: Ctx, f, r: Ref) -> None:
    spec = c.spec
    u = unit_of(spec, Ref("flow", f.name)).split("/")[0].strip()
    v = base_unit(unit_of(spec, r))
    ratio = _free(f"{u}-per-{v}".replace(" ", "-"), c.taken)
    path = _section_file(spec, f)
    items = causes_of(f) + [(f"auxiliary.{ratio}", 1, False)]
    edits = [ye.add_entries(path, "auxiliaries", [[f"  {ratio}:", f"    unit: {u}/{v}", "    exogenous: true",
                                                    f"    description: how many {u} {f.name} moves for each {v} of {r.name} "
                                                    f"(proposed by ergostat)"]]),
             _driven_edit(f, f.name, items)]
    c.add("a new converting auxiliary", "units-mismatch", f"flow.{f.name}", f"An auxiliary {ratio} converting {r.name} into {f.name}",
          [f"flow.{f.name}", str(r), f"auxiliary.{ratio}"],
          f"{f.name} is in {u} and driven by {r.name} in {unit_of(spec, r)}, with nothing between that converts one into the "
          f"other: a coflow moves so many of its units for each of the other's. The auxiliary says how many.",
          "a structural check (ergostat check: units-mismatch), dimensional consistency", edits,
          touched=[f"flow.{f.name}"], finding="units-mismatch")


def equation_sign(c: Ctx, kind: str, x, ref: str, flip: bool) -> None:
    items = []
    for r, sg, ins in causes_of(x):
        if r == ref:
            sg = (-sg if sg else sg) if flip else None
        items.append((r, sg, ins))
    was = x.polarity.get(ref)
    c.add("a link's sign flipped" if flip else "a link's sign taken off", "equation-sign", f"{kind}.{x.name}",
          f"The link {ref} → {x.name}: {'+' if was and was > 0 else '−'} becomes "
          f"{('−' if was and was > 0 else '+') if flip else 'unsigned'}",
          [f"{kind}.{x.name}", ref],
          (f"{x.name}'s equation moves it the other way from the sign drawn (∂{x.name}/∂{ref.split('.', 1)[1]} is "
           f"{'negative' if was and was > 0 else 'positive'} wherever it was tried), so every loop drawn through the link has the "
           f"wrong polarity; the sign is made the equation's.") if flip else
          (f"{x.name}'s equation's effect of {ref} changes sign across the range tried, so the link has no one polarity."),
          "a structural check (ergostat check: equation-sign), the equation's partial derivative by central differences at "
          "seven operating points", [_driven_edit(x, x.name, items)], touched=[f"{kind}.{x.name}"])


def _wrap_max(text: str) -> str:
    return f"MAX(0, {text})"


def _zidz(tree):
    tag = tree[0]
    if tag == "bin":
        a, b = _zidz(tree[2]), _zidz(tree[3])
        if tree[1] == "/" and b[0] not in ("num", "par"):
            return ("fn", "ZIDZ", [a, b])
        return ("bin", tree[1], a, b)
    if tag == "neg":
        return ("neg", _zidz(tree[1]))
    if tag == "fn":
        return ("fn", tree[1], [_zidz(a) for a in tree[2]])
    return tree


def guard(c: Ctx, ref: str, what: str, msg: str) -> None:
    kind, _, name = ref.partition(".")
    x = (c.spec.flows if kind == "flow" else c.spec.auxiliaries).get(name)
    if x is None or x.equation is None:
        return
    text = x.equation.text
    if what == "backwards":
        new, how, change = _wrap_max(text), "MAX(0, …): a one-way flow never runs backwards", "a guard on an equation"
    elif what.startswith("fault:") and "division" in what:
        new = eq.text(_zidz(x.equation.tree))
        how, change = "ZIDZ(a, b): 0 where it would divide by 0", "a guard on an equation"
        if new == text:
            return
    else:
        c.not_made.append({"title": f"A guard on {name}", "code": "extreme-conditions",
                           "why": f"{what}: ergostat cannot write this guard yet ({msg.split('(the extreme')[0].strip()})"})
        return
    path, at = _name_at(x, name)
    c.add(change, "extreme-conditions", ref, f"{name}'s equation guarded: {new}", [ref],
          f"{msg.split('. ')[0]}. With the guard its equation is {new}: {how}.",
          "the extreme-conditions test (ergostat check): the equations run with no record for ten of their slowest time "
          "constant from each extreme condition, confirmed on a grid eight times finer",
          [ye.set_key(path, at, "equation", new)], touched=[ref])


def exogenous(c: Ctx, a) -> None:
    path, at = _name_at(a, a.name)
    c.add("an auxiliary marked exogenous", "auxiliary-without-causes", f"auxiliary.{a.name}", f"{a.name} marked exogenous: true",
          [f"auxiliary.{a.name}"],
          f"nothing drives {a.name} and it is not marked as an input from outside, so the model cannot say why it changes. "
          f"If nothing in the model moves it, it is exogenous; if something does, name it instead (driven-by), by hand.",
          "a structural check (ergostat check: auxiliary-without-causes)", [ye.set_key(path, at, "exogenous", "true")],
          finding="auxiliary-without-causes")


def from_findings(c: Ctx) -> None:
    spec = c.spec
    from ..spec import findings as fd
    found: list[tuple[str, str, str]] = []
    fd.structure(spec, lambda code, msg, w, about: found.append((code, about, msg)))
    for p in getattr(c.p.model, "problems", None) or []:
        if p.code in ("equation-sign", "extreme-conditions"):
            found.append((p.code, p.about, p.message))
    seen = set()
    for code, about, msg in found:
        if (code, about, msg) in seen:
            continue
        seen.add((code, about, msg))
        kind, _, name = about.partition(".")
        try:
            if code == "rate-driven-by-rate":
                f = spec.flows[name]
                rates = [r for r in f.driven_by if r.kind == "flow" and str(r) not in f.instant]
                if rates:
                    rate_driven_by_rate(c, f, rates[0])
            elif code == "stock-without-outflow":
                stock_without_outflow(c, spec.stocks[name])
            elif code == "units-mismatch":
                f = spec.flows[name]
                mine = base_unit(unit_of(spec, Ref("flow", f.name)))
                odd = [r for r in f.driven_by if r.kind == "flow" and mine and (b := base_unit(unit_of(spec, r))) and b != mine]
                if odd:
                    units_mismatch(c, f, odd[0])
            elif code == "auxiliary-without-causes":
                exogenous(c, spec.auxiliaries[name])
            elif code == "equation-sign":
                x = (spec.flows if kind == "flow" else spec.auxiliaries)[name]
                import re
                m = re.search(r"driven-by [+-]?((?:stock|flow|auxiliary)\.[\w-]+)", msg)
                if m:
                    equation_sign(c, kind, x, m.group(1), flip="the other way" in msg)
            elif code == "extreme-conditions":
                what = ("backwards" if "negative rate" in msg else "negative" if "below empty" in msg else
                        "fault:division" if "divid" in msg or "division" in msg else "other")
                guard(c, about, what, msg)
        except (KeyError, ye.EditError) as e:
            c.not_made.append({"title": f"{code} on {about}", "code": code, "why": str(e)})


# ---- what the estimators support: a term with no effect, a sign the record contradicts

def _terms(tree) -> tuple[list, callable] | None:
    """An equation as a sum of terms (inside MAX(0, …) too), and how to write it back from a list of them."""
    if tree[0] == "fn" and tree[1] == "MAX" and len(tree[2]) == 2 and tree[2][0] == ("num", 0.0):
        got = _terms(tree[2][1])
        if got is None:
            return None
        ts, back = got
        return ts, lambda xs: ("fn", "MAX", [("num", 0.0), back(xs)])
    out = []

    def go(n, sign):
        if n[0] == "bin" and n[1] in "+-":
            go(n[2], sign)
            go(n[3], sign if n[1] == "+" else -sign)
        else:
            out.append((sign, n))
    go(tree, 1)

    def back(xs):
        if not xs:
            return ("num", 0.0)
        acc = xs[0][1] if xs[0][0] > 0 else ("neg", xs[0][1])
        for s, n in xs[1:]:
            acc = ("bin", "+" if s > 0 else "-", acc, n)
        return acc
    return out, back


def _product(n) -> tuple[str, str] | None:
    """``k * stock.x`` (either way round): the parameter and the part."""
    if n[0] == "bin" and n[1] == "*":
        a, b = n[2], n[3]
        if a[0] == "par" and b[0] == "ref":
            return a[1], f"{b[1]}.{b[2]}"
        if b[0] == "par" and a[0] == "ref":
            return b[1], f"{a[1]}.{a[2]}"
    return None


def no_effect(c: Ctx) -> None:
    spec = c.spec
    if c.data is None:
        return
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for x in table.values():
            if x.equation is None:
                continue
            got = _terms(x.equation.tree)
            if got is None:
                continue
            terms, back = got
            ref = f"{kind}.{x.name}"
            size = [abs(v) for v in c.level(ref)] or None
            for i, (_, n) in enumerate(terms):
                pr = _product(n)
                if pr is None:
                    continue
                k, cause = pr
                e = c.estimates.get(k)
                if not e or e.get("value") is None or e.get("se") is None or len(terms) < 2:
                    continue
                v, se = e["value"], e["se"]
                cv = [abs(t) for t in c.level(cause)]
                if not cv or abs(v) >= 2 * se:
                    continue                                  # told apart from 0: it has an effect
                base = (sum(size) / len(size)) if size else None
                if not base:
                    continue
                biggest = (abs(v) + 2 * se) * max(cv)
                if biggest >= NARROW * base:
                    continue                                  # 0 cannot be told from a large effect: not narrow
                rest = [t for j, t in enumerate(terms) if j != i]
                new = eq.text(back(rest))
                path, at = _name_at(x, x.name)
                items = [t for t in causes_of(x) if t[0] != cause]
                edits = [ye.set_key(path, at, "equation", new)]
                if any(t[0] == cause for t in causes_of(x)):
                    edits.append(_driven_edit(x, x.name, items))
                still = [y for y in (*spec.flows.values(), *spec.auxiliaries.values())
                         if y.equation and y is not x and k in y.equation.parameters]
                prm = spec.parameters.get(k)
                if not still and prm is not None:
                    pp, pa = _name_at(prm, k)
                    edits.append(ye.remove_entry(pp, pa))
                c.add("a term and its link removed", "no-effect", ref, f"{cause.split('.', 1)[1]} taken out of {x.name}'s equation",
                      [ref, cause],
                      f"{k}, the coefficient of {cause} in {x.name}, is estimated at {ye.number(v)} ± {ye.number(se)}: "
                      f"indistinguishable from 0, and narrowly (at most ±{ye.number(biggest)} over the record, under a tenth "
                      f"of {x.name}'s size, {ye.number(base)}). The data says the link has no effect worth drawing.",
                      f"weighted least squares on the replay ({e.get('scope_words') or 'each part alone'}), "
                      f"{e.get('n', '?')} points: the estimate and its standard error (Gauss–Newton)", edits, touched=[ref])


def contradicted_signs(c: Ctx) -> None:
    from . import estimate as es
    spec, data = c.spec, c.data
    if data is None:
        return
    for f in spec.flows.values():
        if f.equation or f.rate is not None or not f.driven_by or spec.actuator_of(f.name) is not None:
            continue
        target = f"flow.{f.name}"
        causes = [f"{r.kind}.{r.name}" for r in f.driven_by]
        if not c.level(target) or any(not c.level(x) for x in causes) or ob.from_its_stock(spec, target):
            continue
        own = f"stock.{f.source}" if f.source else None
        if own and own not in causes:
            continue
        got = es.linear(data, target, causes, intercept=not own, times=own)
        if got is None or got["r2"] is None or got["r2"] < 0.5:
            continue
        coef = list(got["coef"])
        others = [r for r in f.driven_by if f"{r.kind}.{r.name}" != own]
        per = coef[1:] if (own or got["intercept"]) else coef
        for r, k in zip(others, per, strict=False):
            s = f.polarity.get(str(r))
            if s is None or k * s >= 0:
                continue
            items = [(x, -sg if x == str(r) and sg else sg, ins) for x, sg, ins in causes_of(f)]
            c.add("a link's sign flipped", "sign-contradicted", target,
                  f"The link {r} → {f.name}: {'+' if s > 0 else '−'} becomes {'−' if s > 0 else '+'}", [target, str(r)],
                  f"{f.name} is drawn {'rising' if s > 0 else 'falling'} as {r.name} rises, but on the record it does the "
                  f"opposite: a least-squares fit of {f.name} on its declared causes explains {got['r2']:.0%} of its readings "
                  f"with {r.name}'s coefficient {ye.number(k)}. Until the sign agrees, no equation is proposed for it.",
                  f"ordinary least squares of {f.name}'s readings on its declared causes ({got['n']} points, R² = 1 − SSE/SST)",
                  [_driven_edit(f, f.name, items)], touched=[target])


# ---- simplify (SD Lab's SPEC §4.8 and static/simplify.js, as tested there)

def _entry(spec: Spec, ref: str):
    kind, _, name = ref.partition(".")
    return {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}[kind].get(name)


def _remove_stock_edits(c: Ctx, st) -> list[ye.Edit]:
    """The stock taken away, and each flow's end at it made a cloud (a flow left with no end goes too)."""
    edits = []
    path, at = _name_at(st, st.name)
    edits.append(ye.remove_entry(path, at))
    for f in c.spec.flows_of(st.name):
        ends = [x for x in (f.source, f.target) if x and x != st.name]
        fp, fa = _name_at(f, f.name)
        if not ends:
            edits.append(ye.remove_entry(fp, fa))
            continue
        e = ye.remove_key(fp, fa, "from" if f.source == st.name else "to")
        if e:
            edits.append(e)
    return edits


def simplify(c: Ctx, base_fit: dict | None) -> None:
    spec, data = c.spec, c.data
    if data is None:
        return
    rates = {n: [abs(v) for v in c.level(f"flow.{n}")] for n in spec.flows}
    means = [sum(v) / len(v) for v in rates.values() if v and sum(v) > 0]
    typical = sum(means) / len(means) if means else 1.0
    for n, f in spec.flows.items():                     # a measured flow that moved essentially nothing
        ref = f"flow.{n}"
        if ref in c.named or f.equation is not None or len(rates[n]) < MIN_READINGS or data.how.get(ref) in ("declared", "not measured"):
            continue
        r = rates[n]
        if sum(r) / len(r) < DEAD_MEAN * typical and max(r) < DEAD_PEAK * typical:
            path, at = _name_at(f, n)
            c.add("a flow removed", "simplify-dead-flow", ref, f"Remove {n}", [ref],
                  f"{n} moved essentially nothing over the record (at most {ye.number(max(r))} an hour, where flows here usually "
                  f"move {ye.number(typical)}); a flow that mattered once would have moved more at least once.",
                  f"SD Lab's simplify rule (a measured flow under {DEAD_MEAN:g} of the typical flow on average and "
                  f"{DEAD_PEAK:g} at its peak)",
                  [ye.remove_entry(path, at)], touched=[x for x in (f"stock.{f.source}" if f.source else None,
                                                                    f"stock.{f.target}" if f.target else None) if x])
    if base_fit and (base_fit.get("total") or {}).get("nmse") is not None:      # an equation-only flow that explains nothing
        b = base_fit["total"]["nmse"]
        for n, f in spec.flows.items():
            ref = f"flow.{n}"
            if ref in c.named or f.equation is None or c.level(ref) or f.sensors:
                continue
            path, at = _name_at(f, n)
            edit = ye.remove_entry(path, at)
            try:
                after = tr.spec_after(c.p, [edit])
            except (tr.TrialError, ye.EditError):
                continue
            _, fit = tr.fit_of(after, ob.measured(c.p, data.grid, after))
            a = (fit.get("total") or {}).get("nmse")
            if a is not None and a <= b * NO_WORSE + 1e-12:
                c.add("a flow removed", "simplify-no-effect", ref, f"Remove {n}", [ref],
                      f"{n} is worked out by its equation and measured by nothing; the replay without it fits the stocks "
                      f"{'better' if a < b else 'as well'} (scaled error {b:.3g} → {a:.3g}), so its equation explains nothing "
                      f"the record shows.", f"SD Lab's simplify rule: the replay run again without it, within {NO_WORSE - 1:.0%}",
                      [edit], touched=[f"stock.{s}" for s in (f.source, f.target) if s])
    pairs: dict[tuple, list] = {}                         # two flows between the same two stocks
    for f in spec.flows.values():
        if f.source and f.target:
            pairs.setdefault((f.source, f.target), []).append(f)
    for (a, b), fs in pairs.items():
        if len(fs) < 2 or any(f"flow.{f.name}" in c.named for f in fs):
            continue
        first, rest = fs[0], fs[1:]
        if any(g.sensors for g in rest) and first.sensors:
            c.not_made.append({"title": f"Merge {' and '.join(f.name for f in fs)}", "code": "simplify-merge",
                               "why": "each is measured: merged, one's readings would be lost"})
            continue
        eqs = [g.equation.text for g in fs if g.equation]
        edits = []
        fp, fa = _name_at(first, first.name)
        if eqs and len(eqs) == len(fs):
            edits.append(ye.set_key(fp, fa, "equation", " + ".join(f"({t})" if "+" in t or "-" in t else t for t in eqs)))
            causes = list(dict.fromkeys(x for g in fs for x in causes_of(g)))
            edits.append(_driven_edit(first, first.name, causes))
        elif eqs:
            c.not_made.append({"title": f"Merge {' and '.join(f.name for f in fs)}", "code": "simplify-merge",
                               "why": "one has an equation and the other does not"})
            continue
        for g in rest:
            gp, ga = _name_at(g, g.name)
            edits.append(ye.remove_entry(gp, ga))
        c.add("two flows merged", "simplify-merge", f"flow.{first.name}", f"Merge {' and '.join(f.name for f in fs)} into {first.name}",
              [f"flow.{f.name}" for f in fs],
              f"they all move things from {a} to {b}: one flow can carry them.",
              "SD Lab's simplify rule (two flows between the same two stocks), on the structure", edits,
              touched=[f"stock.{a}", f"stock.{b}"])
    levels = {n: c.level(f"stock.{n}") for n in spec.stocks}
    for n, st in spec.stocks.items():
        ref = f"stock.{n}"
        if ref in c.named or st.cumulative:
            continue
        touching = spec.flows_of(n)
        lv = levels[n]
        if not touching:
            path, at = _name_at(st, n)
            c.add("a stock removed", "simplify-alone", ref, f"Remove {n}", [ref],
                  f"no flow touches {n} and no goal holds it: nothing in the model moves it or depends on it "
                  f"(ergostat has no hide:, so this removes it; its readings stay in the record).",
                  "SD Lab's simplify rule (a stock nothing touches, with no goal), on the structure", [ye.remove_entry(path, at)])
            continue
        if len(lv) < MIN_READINGS:
            continue
        lo, hi, m = min(lv), max(lv), sum(abs(v) for v in lv) / len(lv)
        if m > 0 and hi - lo <= max(1e-9, STILL * m):
            c.add("a stock removed", "simplify-still", ref, f"Remove {n}", [ref, *(f"flow.{f.name}" for f in touching)],
                  f"{n} never changed over the record ({ye.number(lo)} the whole time): it acts like a setting, not a stock. "
                  f"ergostat has no hide:, so this removes it, and its flows' ends there become clouds.",
                  f"SD Lab's simplify rule (a range under {STILL:g} of its mean, {len(lv)} readings)", _remove_stock_edits(c, st))
            continue
        empty = sum(1 for v in lv if abs(v) < EMPTY) / len(lv)
        if empty >= NEARLY_ALWAYS:
            ins = [f for f in touching if f.target == n and f.source]
            outs = [f for f in touching if f.source == n and f.target]
            if len(ins) == 1 and len(outs) == 1 and len(touching) == 2 and ins[0].source != outs[0].target \
                    and not ({f"flow.{ins[0].name}", f"flow.{outs[0].name}"} & c.named):
                a, b = ins[0], outs[0]
                ap, aa = _name_at(a, a.name)
                bp, ba = _name_at(b, b.name)
                sp_, sa = _name_at(st, n)
                edits = [ye.set_key(ap, aa, "to", b.target), ye.remove_entry(bp, ba), ye.remove_entry(sp_, sa)]
                c.add("a pass-through joined", "simplify-pass-through", ref, f"Connect {a.source} straight to {b.target}",
                      [ref, f"flow.{a.name}", f"flow.{b.name}"],
                      f"{n} is empty at {empty:.0%} of its readings: things pass straight through it. {a.name} can go straight "
                      f"to {b.target}, replacing {b.name}, and {n} goes (ergostat has no hide:, so it is removed).",
                      f"SD Lab's simplify rule (empty, under {EMPTY:g}, at {NEARLY_ALWAYS:.0%} of readings or more; one flow in "
                      f"from a stock and one out to a stock)", edits, touched=[f"stock.{a.source}", f"stock.{b.target}"])
            else:
                c.add("a stock removed", "simplify-empty", ref, f"Remove {n}", [ref, *(f"flow.{f.name}" for f in touching)],
                      f"{n} is empty at {empty:.0%} of its readings: what flows through it does not stay. ergostat has no hide:, "
                      f"so this removes it, and its flows' ends there become clouds.",
                      f"SD Lab's simplify rule (empty, under {EMPTY:g}, at {NEARLY_ALWAYS:.0%} of readings or more)",
                      _remove_stock_edits(c, st))
    names = [n for n in spec.stocks if f"stock.{n}" not in c.named and len(levels[n]) >= MIN_READINGS and not spec.stocks[n].cumulative]
    full = {n: c.data.values.get(f"stock.{n}") or [] for n in names}
    for i, a in enumerate(names):                        # twins: two stocks that move exactly alike
        for b in names[i + 1:]:
            pts = [(x, y) for x, y in zip(full[a], full[b], strict=False) if x is not None and y is not None]
            if len(pts) < MIN_READINGS:
                continue
            ma, mb = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
            sab = sum((x - ma) * (y - mb) for x, y in pts)
            saa, sbb = sum((x - ma) ** 2 for x, _ in pts), sum((y - mb) ** 2 for _, y in pts)
            if saa < 1e-9 or sbb < 1e-9:
                continue
            corr, scale = sab / math.sqrt(saa * sbb), math.sqrt(sbb / saa)
            if corr > TWIN and abs(math.log(scale)) < 0.05:
                st = spec.stocks[b]
                c.add("a stock removed", "simplify-twin", f"stock.{b}", f"Remove {b}, a twin of {a}",
                      [f"stock.{b}", f"stock.{a}", *(f"flow.{f.name}" for f in spec.flows_of(b))],
                      f"{b} moves exactly like {a} (correlation {corr:.4f}, scale {scale:.3f}): probably the same thing "
                      f"measured twice. ergostat has no hide:, so this removes {b}, and its flows' ends there become clouds.",
                      f"SD Lab's simplify rule (correlation past {TWIN}, scale within 5%, {len(pts)} readings together)",
                      _remove_stock_edits(c, st), touched=[f"stock.{a}"])


def from_residuals(c: Ctx) -> None:
    """The residual-pattern structure finder: a missing stock, flow or delay, or a part replaced, from the
    pattern in what the model fails to explain (SD Lab's discovery: hidden stocks as delayed copies of
    measured ones, judged on whether the model with them fits about as well or better). Not built yet: the
    next piece of work. Until then it proposes nothing, and the Fit page says what it will propose."""
    return None


def _span(hours: float) -> str:
    from ..durations import human
    return human(hours * 3600.0)


def find(p, spec: Spec, data: ob.Data | None, estimates: dict | None = None, base_fit: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Every structural change ergostat can propose for the model as it is, and the ones it found and could
    not make (with why)."""
    c = Ctx(p, spec, data, estimates)
    from_findings(c)
    no_effect(c)
    contradicted_signs(c)
    simplify(c, base_fit)
    from_residuals(c)
    seen, out = set(), []
    for x in c.out:
        if x["id"] not in seen:
            seen.add(x["id"])
            out.append(x)
    return out, c.not_made
