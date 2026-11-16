"""Proposals: each a concrete change to the model, with its reason, the fit before and after, and the
smallest edit to the YAML that makes it. Nothing here changes the model by itself: a proposal is
listed until the owner accepts it (the edit is applied, ``ergostat check`` must still pass, and the
model's history records the change and its fit before and after) or dismisses it (it is not made
again for this structure).

Two kinds so far:

- **parameter**: a parameter marked ``estimate: true`` set to its estimate, when the estimate fits
  better than the value written;
- **equation**: a flow with declared causes and no equation given one, a coefficient for each
  cause, fitted by least squares on what was measured (an outflow with no constant term: with its
  stock empty it stops).

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
from . import simulate as sim
from . import version as ver
from . import yamledit as ye

FILE = "proposals.json"
CHANGED = 0.02           # a parameter's estimate is proposed when it moves the value by more than this share
BETTER = 0.99            # ... and fits at least this much better (its cost after over before)
EQUATION_R2 = 0.5        # an equation is proposed when it explains this much of its flow's readings


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


def _total(spec: Spec, data: sim.Data, pl: sim.Plan) -> dict:
    got = ft.compare(spec, data, sim.replay(spec, data, pl))
    return {"total": ft._slim(got["total"]), "stocks": {r: ft._slim(s) for r, s in got["stocks"].items()},
            "equations": {r: ft._slim(s) for r, s in got["equations"].items()}}


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


def make(p, snap: dict, n: int | None = None) -> list[dict]:
    """Estimate, then propose: every change the record supports, for the model as it is now. Pending
    proposals for an older structure are let go; accepted and dismissed ones are kept."""
    spec: Spec = p.model.spec
    since, until = series.span(p, snap)
    data = sim.measured(p, sim.Grid(since, until, n or series.POINTS))
    estimates = es.estimate(p, snap, n)
    st, v = ver.structure(spec), ver.version(spec)
    base = sim.plan(spec)
    before = _total(spec, data, base)
    now = time.time()
    found: list[dict] = []
    groups: dict[tuple, list[str]] = {}
    for name, e in sorted(estimates.items()):           # parameters fitted together are proposed together
        prm = spec.parameters.get(name)
        if prm is None or e.get("value") is None or not prm.estimate:
            continue
        groups.setdefault(tuple(sorted([name, *e.get("with", [])])), []).append(name)
    for group in groups.values():
        e = estimates[group[0]]
        moved = {}
        for name in group:
            old, new = spec.parameters[name].value, float(ye.number(estimates[name]["value"]))
            if old is None or abs(new - old) > CHANGED * max(abs(old), 1e-12):
                moved[name] = new
        if not moved:
            continue
        if all(spec.parameters[n].value is not None for n in moved) and not (e["after"] < e["before"] * BETTER):
            continue
        after = _total(spec, data, sim.plan(spec, moved))
        edits, errors = [], []
        for name, new in moved.items():
            try:
                edits.append(_value_edit(spec.parameters[name], new))
            except ye.EditError as err:
                errors.append(str(err))

        def said(name, v):
            x = spec.parameters[name]
            return "no value" if v is None else ye.duration(v) if x.duration else f"{ye.number(v)}{' ' + x.unit if x.unit else ''}"
        found.append({
            "id": _id("parameter", st, sorted(moved.items())), "kind": "parameter",
            "target": ", ".join(f"parameter.{n}" for n in moved), "parameters": moved,
            "previous": {n: spec.parameters[n].value for n in moved},
            "parts": sorted({r for n in moved for r in users_of(spec, n)}), "touched": e.get("fitted_to", []),
            "title": "; ".join(f"{n}: {said(n, spec.parameters[n].value)} → {said(n, v)}" for n, v in moved.items()),
            "reason": (f"estimated {'together ' if len(group) > 1 else ''}from {e['n']} points over the last "
                       f"{series.dur(e['window'])}: what {'they move' if len(group) > 1 else 'it moves'} "
                       f"({', '.join(e['fitted_to'])}) " +
                       (f"follows with R² {e['r2']:.2f}" if e.get("r2") is not None else "follows better") +
                       (f"; its error falls by {1 - e['after'] / e['before']:.0%}" if e["before"] > 0 else "")),
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
                          "window": until - since}
    save(p, props)
    return pending(p, spec)


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


def _equations(spec: Spec, data: sim.Data, before: dict) -> list[dict]:
    out = []
    for f in spec.flows.values():
        if f.equation or f.rate is not None or not f.driven_by or spec.actuator_of(f.name) is not None:
            continue
        target = f"flow.{f.name}"
        if not any(x is not None for x in data.values.get(target) or []):
            continue
        causes = [f"{r.kind}.{r.name}" for r in f.driven_by]
        if any(not any(x is not None for x in data.values.get(c) or []) for c in causes):
            continue
        outflow = bool(f.source and f"stock.{f.source}" in causes)
        got = es.linear(data, target, causes, intercept=not outflow)
        if got is None or got["r2"] is None or got["r2"] < EQUATION_R2:
            continue
        coef = got["coef"][1:] if got["intercept"] else got["coef"]
        signs = [f.polarity.get(f"{r.kind}.{r.name}") for r in f.driven_by]
        if any(s is not None and c * s < 0 for c, s in zip(coef, signs, strict=True)):
            continue                                  # a declared sign the record contradicts: a structural question, not a size
        taken = set(spec.parameters)
        names, terms, params = [], [], {}
        want = eq.unit(f"{_unit(spec, f)}/h") if _unit(spec, f) else None
        for r, c in zip(f.driven_by, coef, strict=True):
            nm = _free(f"{f.name}-per-{r.name}", taken)
            taken.add(nm)
            cu = eq.unit(_ref_unit(spec, r))
            unit = unit_words(eq._mul(want, cu, -1)) if want is not None and cu is not None else ""
            params[nm] = (c, unit)
            names.append(nm)
            terms.append(f"{nm} * {r}")
        if got["intercept"]:
            nm = _free(f"{f.name}-base", taken)
            params[nm] = (got["coef"][0], unit_words(want) if want is not None else "")
            terms.insert(0, nm)
        text = " + ".join(terms)
        tree = eq.parse(text, spec.parameters)
        e = Equation(text, tree, eq.refs(tree), eq.names(tree))
        pl = sim.plan(spec, extra={target: e}, extra_params={k: (v, u) for k, (v, u) in params.items()})
        after = _total(spec, data, pl)
        try:
            edit = _equation_edit(spec, f, text, params)
        except ye.EditError as err:
            edit = {"error": str(err)}
        out.append({
            "id": _id("equation", ver.structure(spec), f.name, text), "kind": "equation", "target": target, "parts": [target],
            "touched": [target] + [f"stock.{x}" for x in (f.source, f.target) if x],
            "equation": text, "parameters": {k: {"value": float(ye.number(v)), "unit": u} for k, (v, u) in params.items()},
            "title": f"{f.name} = {text}",
            "reason": (f"its declared causes explain {got['r2']:.0%} of its readings (R², {got['n']} points), with a "
                       f"coefficient for each fitted by least squares" + ("; no constant term, so with its stock empty it "
                                                                         "stops" if outflow else "")),
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
        entries.append([f"  {nm}:", f"    value: {ye.number(v)}"] + ([f"    unit: {u}"] if u else []) +
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
