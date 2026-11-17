"""Proposals: each a concrete change to the model, with its reason, the fit before and after, and the
smallest edit to the YAML that makes it. Nothing here changes the model by itself: a proposal is
listed until the owner accepts it (the edit is applied, ``ergostat check`` must still pass, and the
model's history records the change and its fit before and after) or dismisses it (it is not made
again for this structure).

Two kinds so far:

- **parameter**: a parameter marked ``estimate: true`` set to its estimate, only when the record
  supports it (``estimate.judged``): enough record for the slowest time constant it touches, not at
  its bound, identifiable, more than two standard errors from the value written, and better on the
  record held out. Its reason and its numbers are of the objective that was minimised;
- **equation**: a flow with declared causes and no equation given one, a coefficient for each
  cause, fitted by least squares on what was measured. An outflow is first-order in its stock
  (``stock.x / time-in-x``, with its stock empty it stops) and is proposed only when it names its
  stock as a cause; a one-way flow never runs backwards (``MAX(0, ...)``, its constant term not
  below 0); a flow and a cause inside a loop a controller closes carry the warning that a
  regression there is biased (Ljung ch. 13).

Kept in ``<state>/proposals.json``."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .. import series
from ..spec import equation as eq
from ..spec.ir import Equation, Spec
from . import estimate as es
from . import fit as ft
from . import observe as ob
from . import simulate as sim
from . import version as ver
from . import yamledit as ye

FILE = "proposals.json"
EQUATION_R2 = 0.5        # an equation is proposed when it explains this much of its flow's readings (1 − SSE/SST)


class ProposalError(Exception):
    pass


def path(p) -> Path:
    return p.dir / FILE


def stored(p) -> dict[str, dict]:
    try:
        return json.loads(path(p).read_text())
    except (OSError, ValueError):
        return {}


def save(p, props: dict[str, dict]) -> None:
    f = path(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(props, indent=1))
    tmp.replace(f)


def pending(p, spec: Spec | None = None) -> list[dict]:
    """The proposals waiting for the owner, for the model as it is now."""
    st = ver.structure(spec or p.model.spec)
    return sorted((x for x in stored(p).values() if x["status"] == "pending" and x["structure"] == st),
                  key=lambda x: x["created"])


def _id(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:8]


def _total(spec: Spec, data: ob.Data, pl: sim.Plan) -> dict:
    run = sim.replay(spec, data, pl)
    partial = sim.replay(spec, data, sim.plan(spec, pl.params, None, None, set()))
    got = ft.compare(spec, data, run, partial)
    return {"total": ft._slim(got["total"]), "stocks": {r: ft._slim(s) for r, s in got["stocks"].items()},
            "equations": {r: ft._slim(s) for r, s in got["partial"].items()}}


def _with_extra(spec: Spec, data: ob.Data, extra: dict, params: dict) -> dict:
    pl = sim.plan(spec, extra=extra, extra_params=params)
    run = sim.replay(spec, data, pl)
    partial = sim.replay(spec, data, sim.plan(spec, extra=extra, extra_params=params, integrate=set()))
    got = ft.compare(spec, data, run, partial)
    return {"total": ft._slim(got["total"]), "stocks": {r: ft._slim(s) for r, s in got["stocks"].items()},
            "equations": {r: ft._slim(s) for r, s in got["partial"].items()}}


def users_of(spec: Spec, parameter: str) -> list[str]:
    """The parts whose equations name a parameter."""
    return [f"{k}.{x.name}" for k, t in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)) for x in t.values()
            if x.equation and parameter in x.equation.parameters]


def unit_words(u: dict | None) -> str:
    """A unit as the YAML writes it: ramps/h, 1/h, alerts/ramp; empty for none."""
    if u is None or not u:
        return ""
    top = "·".join(w if p == 1 else f"{w}^{p}" for w, p in sorted(u.items()) if p > 0) or "1"
    bottom = "/".join(w if p == -1 else f"{w}^{-p}" for w, p in sorted(u.items()) if p < 0)
    return top + (f"/{bottom}" if bottom else "")


def make(p, snap: dict | None = None, n: int | None = None) -> list[dict]:
    """Estimate, then propose: every change the record supports, for the model as it is now, on the
    reference window (never the page's). Pending proposals for an older structure are let go;
    accepted and dismissed ones are kept. An estimate the record does not support is kept with why
    (``estimate.judged``), shown beside its parameter, and proposes nothing."""
    spec: Spec = p.model.spec
    data = ob.measured(p, ob.reference(p, (snap or {}).get("at"), n))
    estimates = es.estimate(p, snap, n)
    st, v = ver.structure(spec), ver.version(spec)
    base = sim.plan(spec)
    before = _total(spec, data, base)
    now = time.time()
    found: list[dict] = []
    groups: dict[tuple, list[str]] = {}
    for name, e in sorted(estimates.items()):           # parameters fitted together are proposed together
        prm = spec.parameters.get(name)
        if prm is None or not prm.estimate:
            continue
        e["refused"] = es.judged(e, prm.value)
        groups.setdefault(tuple(sorted([name, *e.get("with", [])])), []).append(name)
    _keep_judgements(p, spec, estimates)
    for group in groups.values():
        if any(estimates[n].get("value") is None for n in group):
            continue
        e = estimates[group[0]]
        sure = [n for n in group if estimates[n]["refused"] is None]
        if not sure:
            continue
        moved = {name: float(ye.number(estimates[name]["value"])) for name in sure}
        after = _total(spec, data, sim.plan(spec, moved))
        edits, errors = [], []
        for name, new in moved.items():
            try:
                edits.append(_value_edit(spec.parameters[name], new))
            except ye.EditError as err:
                errors.append(str(err))

        def said(name, v, se=None):
            x = spec.parameters[name]
            if v is None:
                return "no value"
            num = ye.duration(v) if x.duration else f"{ye.number(v)}{' ' + x.unit if x.unit else ''}"
            return num if se is None else f"{num} ± {ye.duration(se) if x.duration else ye.number(se)}"
        corr = [(a, b, c) for a in sure for b, c in (estimates[a].get("corr") or {}).items() if a < b and c is not None]
        objective = {"before": e["before"], "after": e["after"], "held_before": e.get("held_before"),
                     "held_after": e.get("held_after")}
        fall = 1 - e["after"] / e["before"] if e["before"] > 0 else None
        held = (1 - e["held_after"] / e["held_before"] if e.get("held_before") and e.get("held_after") is not None else None)
        found.append({
            "id": _id("parameter", st, sorted(moved.items())), "kind": "parameter",
            "target": ", ".join(f"parameter.{n}" for n in moved), "parameters": moved,
            "previous": {n: spec.parameters[n].value for n in moved},
            "uncertainty": {n: es.said_se(estimates[n], moved[n]) for n in moved},
            "parts": sorted({r for n in moved for r in users_of(spec, n)}), "touched": e.get("fitted_to", []),
            "title": "; ".join(f"{n}: {said(n, spec.parameters[n].value)} → {said(n, v, es.said_se(estimates[n], v))}"
                               for n, v in moved.items()),
            "reason": (f"estimated {'together ' if len(group) > 1 else ''}from {e['n']} points over the last "
                       f"{series.dur(e['window'])}, the last fifth held out, by weighted least squares on "
                       f"{', '.join(e['fitted_to'])}: " +
                       (f"their weighted error falls by {fall:.0%} on the record fitted" if fall is not None else "it fits better") +
                       (f" and by {held:.0%} on the record held out" if held is not None else "") +
                       "".join(f"; {a} and {b} are correlated {c:+.2f}" for a, b, c in corr if abs(c) > 0.5) +
                       (f" (±: one standard error; {', '.join(sorted(set(group) - set(sure)))} not proposed: "
                        f"{'; '.join(estimates[x]['refused'] for x in sorted(set(group) - set(sure)))})" if set(group) - set(sure)
                        else " (±: one standard error)")),
            "objective": objective,
            "estimate": {n: estimates[n] for n in group}, "fit_before": before, "fit_after": after,
            "edit": _joined(edits) if not errors else {"error": "; ".join(errors)}})
    found += _equations(spec, data, before)
    props = stored(p)
    for k in [k for k, x in props.items() if x["status"] == "pending"]:
        del props[k]
    for x in found:
        if x["id"] in props:                       # dismissed (or accepted) already: not made again
            continue
        props[x["id"]] = {**x, "status": "pending", "created": now, "structure": st, "version": v,
                          "window": data.grid.until - data.grid.since}
    save(p, props)
    return pending(p, spec)


def _keep_judgements(p, spec: Spec, estimates: dict) -> None:
    f = es.path(p, ver.structure(spec))
    try:
        f.write_text(json.dumps(estimates, indent=1))
    except OSError:
        pass


def _value_edit(prm, value: float) -> ye.Edit:
    if prm.value_at is None or prm.where is None:
        if prm.defined is None:
            raise ye.EditError(f"parameter {prm.name}: where it is written is not known")
        return ye.add_key(prm.defined.file, prm.defined.line, "value", ye.number(value))
    key = "value" if prm.value_at != prm.defined else prm.name           # the short form, k: 0.45
    return ye.set_value(prm.value_at.file, prm.value_at.line, key, ye.duration(value) if prm.duration else ye.number(value))


def _joined(edits: list) -> dict:
    """Edits to one or more files, as one: each file's hunks together, and one diff to read."""
    by: dict[str, list] = {}
    for e in edits:
        by.setdefault(e.file, []).append(e)
    files = [ye.merge(es_) for es_ in by.values()]
    return {"files": [f.as_dict() for f in files], "diff": "\n".join(f.diff() for f in files)}


def _equations(spec: Spec, data: ob.Data, before: dict) -> list[dict]:
    out = []
    loops = sim.controlled(spec)
    for f in spec.flows.values():
        if f.equation or f.rate is not None or not f.driven_by or spec.actuator_of(f.name) is not None:
            continue
        target = f"flow.{f.name}"
        if not any(x is not None for x in data.values.get(target) or []) or ob.from_its_stock(spec, target):
            continue
        causes = [f"{r.kind}.{r.name}" for r in f.driven_by]
        if any(not any(x is not None for x in data.values.get(c) or []) for c in causes):
            continue
        own = f"stock.{f.source}" if f.source else None
        if own and own not in causes:
            continue                                  # an outflow that ignores its stock: a structural question first
        got = es.linear(data, target, causes, intercept=not own, times=own)
        if got is None or got["r2"] is None or got["r2"] < EQUATION_R2:
            continue
        coef = list(got["coef"])
        others = [r for r in f.driven_by if f"{r.kind}.{r.name}" != own]
        if own:
            share, per = coef[0], coef[1:]
            if share <= 0:
                continue                              # it would drain faster with less there: the structure is wrong
        else:
            base, per = (coef[0], coef[1:]) if got["intercept"] else (0.0, coef)
            if base < 0 and not f.two_way:            # a one-way flow's own rate is never below 0: fit it through 0
                got = es.linear(data, target, causes, intercept=False)
                if got is None or got["r2"] is None or got["r2"] < EQUATION_R2:
                    continue
                base, per = 0.0, list(got["coef"])
        signs = [f.polarity.get(f"{r.kind}.{r.name}") for r in others]
        if any(s is not None and c * s < 0 for c, s in zip(per, signs, strict=True)):
            continue                                  # a declared sign the record contradicts: a structural question, not a size
        taken = set(spec.parameters)
        terms, params = [], {}
        want = eq.unit(f"{_unit(spec, f)}/h") if _unit(spec, f) else None
        for r, c in zip(others, per, strict=True):
            nm = _free(f"{f.name}-per-{r.name}", taken)
            taken.add(nm)
            cu = eq.unit(_ref_unit(spec, r))
            if own:                                   # a fraction of the stock an hour, per unit of the cause
                unit = unit_words(eq._mul({"h": -1}, cu, -1)) if cu is not None else ""
            else:
                unit = unit_words(eq._mul(want, cu, -1)) if want is not None and cu is not None else ""
            params[nm] = (c, unit)
            terms.append(f"{nm} * {r.kind}.{r.name}")
        if own:
            tn = _free(f"time-in-{f.source}", taken)
            params[tn] = (1.0 / share, "h")
            inner = " + ".join([f"1 / {tn}", *terms])
            text = f"{own} / {tn}" if not terms else f"MAX(0, {own} * ({inner}))"
        else:
            if got["intercept"] and base:
                nm = _free(f"{f.name}-base", taken)
                params[nm] = (base, unit_words(want) if want is not None else "")
                terms.insert(0, nm)
            text = " + ".join(terms) if terms else "0"
            negative = any(c < 0 for c in per) or any(x is not None and x < 0 for c in causes for x in data.values.get(c) or [])
            if not f.two_way and negative:            # a one-way flow never runs backwards, whatever its causes do
                text = f"MAX(0, {text})"
        tree = eq.parse(text, spec.parameters)
        e = Equation(text, tree, eq.refs(tree), eq.names(tree))
        after = _with_extra(spec, data, {target: e}, {k: (v, u) for k, (v, u) in params.items()})
        try:
            edit = _equation_edit(spec, f, text, params)
        except ye.EditError as err:
            edit = {"error": str(err)}
        inside = [c for c in causes if c != own and target in loops and c in loops]
        out.append({
            "id": _id("equation", ver.structure(spec), f.name, text), "kind": "equation", "target": target, "parts": [target],
            "touched": [target] + [f"stock.{x}" for x in (f.source, f.target) if x],
            "equation": text, "parameters": {k: {"value": float(ye.number(v)), "unit": u} for k, (v, u) in params.items()},
            "title": f"{f.name} = {text}",
            "reason": (f"its declared causes explain {got['r2']:.0%} of the variation in its readings (R² = 1 − SSE/SST, "
                       f"{got['n']} points), a coefficient for each fitted by least squares" +
                       ("; first-order in its stock (what is there over the time it stays), so with its stock empty it "
                        "stops" if own else "") +
                       ("; it never runs backwards (MAX(0, …))" if text.startswith("MAX(0") else "") +
                       (f"; {target} and {', '.join(inside)} lie in a loop a controller closes, where a regression is "
                        f"biased (the controller makes the cause follow the flow): read the coefficients as a start, not "
                        f"a measurement" if inside else "")),
            "fit_before": before, "fit_after": after, "edit": edit})
    return out


def _unit(spec: Spec, f) -> str:
    from ..spec.findings import unit_of
    from ..spec.ir import Ref
    return unit_of(spec, Ref("flow", f.name))


def _ref_unit(spec: Spec, r) -> str | None:
    from ..spec.equation_checks import expected_unit
    return expected_unit(spec, r.kind, r.name)


def _free(name: str, taken: set[str]) -> str:
    out, i = name, 2
    while out in taken:
        out, i = f"{name}-{i}", i + 1
    return out


def _equation_edit(spec: Spec, f, text: str, params: dict) -> dict:
    if f.defined is None:
        raise ye.EditError(f"flow {f.name}: where it is written is not known")
    path = f.defined.file
    first = ye.add_key(path, f.defined.line, "equation", text)
    entries = []
    for nm, (v, u) in params.items():
        value = ye.duration(v) if u == "h" else ye.number(v)          # a time, written as one (read in hours)
        entries.append([f"  {nm}:", f"    value: {value}"] + ([f"    unit: {u}"] if u and u != "h" else []) +
                       ["    estimate: true          # proposed by ergostat, fitted by least squares; refitted as the record grows"])
    second = ye.add_entries(path, "parameters", entries)
    return _joined([first, second])


def find(p, pid: str) -> dict:
    props = stored(p)
    hits = [x for k, x in props.items() if k.startswith(pid)] if pid else []
    if len(hits) != 1:
        raise ProposalError(f"no proposal {pid}" if not hits else f"{pid} is the start of {len(hits)} proposals: give more of it")
    return hits[0]


def dismiss(p, pid: str) -> dict:
    props = stored(p)
    x = find(p, pid)
    if x["status"] != "pending":
        raise ProposalError(f"proposal {x['id']} is {x['status']} already")
    x["status"], x["decided"] = "dismissed", time.time()
    props[x["id"]] = x
    save(p, props)
    p.events.add("model.dismissed", item=p.model.name, source="owner", data={"proposal": x["id"], "title": x["title"]})
    return x


def accept(p, pid: str, snap: dict, by: str = "owner") -> dict:
    """Apply the proposal's edit, check the model still compiles (else put the file back), record the
    change with the fit before and after, and return what was done."""
    from .. import model as mdl
    from ..spec import read
    props = stored(p)
    x = find(p, pid)
    if x["status"] != "pending":
        raise ProposalError(f"proposal {x['id']} is {x['status']} already")
    if "error" in x["edit"]:
        raise ProposalError(f"its edit cannot be made by ergostat ({x['edit']['error']}); write it by hand")
    if x["structure"] != ver.structure(p.model.spec):
        raise ProposalError("the model has changed since it was proposed: ask for proposals again")
    edits = [ye.Edit.from_dict(d) for d in x["edit"]["files"]]
    old_text = {e.file: Path(e.file).read_text(encoding="utf-8") for e in edits}
    _, _, fit_before = ft.compute(p, snap)
    v_before = ver.version(p.model.spec)
    try:
        new_text = {e.file: ye.apply(e) for e in edits}           # every file checked before any is written
    except ye.EditError as e:
        raise ProposalError(str(e)) from None
    ft.record(p, fit_before, snap["window"], force=True)             # the version it leaves, as it fitted at the end
    for f, text in new_text.items():
        Path(f).write_text(text, encoding="utf-8")
    _, problems = read(p.model.path)
    errors = [str(e) for e in problems if e.level == "error"]
    if errors:
        for f, text in old_text.items():
            Path(f).write_text(text, encoding="utf-8")
        raise ProposalError("the edit would leave the model with errors, so it was not made:\n  " + "\n  ".join(errors))
    p.model = mdl.load(p.model.path.parent)
    _, _, fit_after = ft.compute(p, snap)
    ft.record(p, fit_after, snap["window"], force=True)
    x["status"], x["decided"], x["by"] = "accepted", time.time(), by
    x["applied"] = {"version_before": v_before, "version_after": ver.version(p.model.spec),
                    "fit_before": ft._slim(fit_before["total"]), "fit_after": ft._slim(fit_after["total"])}
    props[x["id"]] = x
    save(p, props)
    p.events.add("model.accepted", item=p.model.name, source=by,
                 data={"proposal": x["id"], "kind": x["kind"], "title": x["title"], "target": x["target"],
                       "diff": x["edit"]["diff"], **x["applied"]})
    return x


def accepted(p, since: float | None = None) -> list[dict]:
    """The changes accepted, oldest first: the model's history of what the record taught it."""
    return [{"time": e["time"], **e["data"]} for e in p.events.query(n=None, type="model.accepted", since=since)]
