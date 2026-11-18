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

A third, the owner's what-if (``propose_values``); and the structural proposals (``structural.py``) are
kept here too, so they are accepted and dismissed the same way. All are read as one review queue
(``review.py``). Kept in ``<state>/proposals.json``."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import time
from pathlib import Path

from .. import series
from ..spec import equation as eq
from ..spec.ir import MODEL_CHANGE, Equation, Spec
from . import estimate as es
from . import fit as ft
from . import observe as ob
from . import simulate as sim
from . import version as ver
from . import yamledit as ye

EQUATION_R2 = 0.5        # an equation is proposed when it explains this much of its flow's readings (1 − SSE/SST)
OPEN = ("checked", "testing", "passed")                 # waiting: in the review queue
STATUS = {"made": "made", "checked": "pending", "testing": "pending", "passed": "pending", "accepted": "accepted",
          "refused": "refused", "failed": "failed", "dismissed": "dismissed", "superseded": "superseded",
          "verified": "accepted", "regressed": "accepted",           # scored again after it was written (verify.py)
          "inconclusive": "inconclusive"}                              # the judge could not tell: it needs more record
_FOLDED: dict = {}


class ProposalError(Exception):
    pass


def item_of(pid: str) -> str:
    return f"{MODEL_CHANGE}/{pid}"


def changes(p) -> dict[str, tuple[str, dict]]:
    """Every change to the model in the record, folded (``ergostat.model-change`` items) as every item is
    (SPEC §5a: each event's changeset in turn, by the built-in kind's rules): its id, its state and its fields.
    The record is the only store."""
    from ..spec import items as its
    from ..spec.ir import model_change_kind
    key = (str(p.dir), p.events.last_seq())
    got = _FOLDED.get(key[0])
    if got and got[0] == key[1]:
        return got[1]
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{MODEL_CHANGE}.*"):
        if "/" in str(e.get("item") or ""):
            by.setdefault(e["item"], []).append(e)
    kind = model_change_kind()
    out: dict[str, tuple[str, dict]] = {}
    for item, evs in by.items():
        it = its.fold(item, evs, kind)
        out[item.split("/", 1)[1]] = (it.state, it.fields)
    _FOLDED[key[0]] = (key[1], out)
    return out


def stored(p) -> dict[str, dict]:
    """The changes to the model, as the review queue reads them: each with its ``status`` (pending while it is
    checked, testing or passed; else what became of it) and its ``state``. One superseded is as if never made: it
    may be made again."""
    return {pid: {**f, "id": pid, "state": st, "status": STATUS[st]} for pid, (st, f) in changes(p).items()
            if st != "superseded"}


@contextlib.contextmanager
def locked(p):
    """Held while the changes are read, changed and recorded back, so a block's proposal arriving in the engine and
    the judge in its own thread never record over each other."""
    p.dir.mkdir(parents=True, exist_ok=True)
    with open(p.dir / "proposals.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def candidate(x: dict) -> bool:
    """A change ergostat's own finders never let go when they look again: one a block made, or one under test or
    passed by the judge."""
    return bool(x.get("made_by") and x["made_by"] not in ("ergostat", "owner")) or x.get("state") in ("testing", "passed")


def event(p, pid: str, state: str, data: dict | None = None, source: str = "ergostat", causedby: str | None = None) -> dict:
    """One step of a change to the model, recorded: ``ergostat.model-change.<state>`` about its item."""
    return p.events.add(f"{MODEL_CHANGE}.{state}", item=item_of(pid), source=source, causedby=causedby, data=data or {})


DECIDED = {"accepted", "dismissed", "refused", "failed", "superseded", "inconclusive"}
LOCAL = ("id", "status", "state")


def save(p, props: dict[str, dict]) -> None:
    """What changed in ``props`` since ``stored``, recorded as events: a new change made (by its ``made_by``, else
    ergostat) and checked; one left out superseded; a status or state moved, with the fields that changed; fields
    alone changed, as its state again."""
    now = stored(p)
    for pid, x in props.items():
        was = now.get(pid)
        body = {k: v for k, v in x.items() if k not in LOCAL}
        if was is None:
            body.setdefault("made_by", "owner" if x.get("scope") == "what-if" else "ergostat")
            event(p, pid, "made", body, source=body["made_by"], causedby=x.get("run"))
            st = x.get("state") if x.get("state") not in (None, "made") else \
                {"pending": "checked", "made": None}.get(x.get("status", "pending"), x.get("status"))
            if st and st != "made":
                event(p, pid, st, {}, source=_decider(x, st))
            continue
        changed = {k: v for k, v in body.items() if json.dumps(v, sort_keys=True, default=str) !=
                   json.dumps(was.get(k), sort_keys=True, default=str)}
        target = x.get("state") if x.get("state") and x.get("state") != was["state"] else \
            (x["status"] if x.get("status") in DECIDED and x["status"] != was["status"] else None)
        if target:
            event(p, pid, target, changed, source=_decider(x, target))
        elif changed:
            event(p, pid, was["state"], changed, source="ergostat")
    for pid in set(now) - set(props):
        event(p, pid, "superseded", {"why": "let go: found again otherwise, or no longer found"})


def _decider(x: dict, state: str) -> str:
    """Who an event of this state is from: who decided (the owner, or the policy, named) for accepted or dismissed;
    ergostat for the rest."""
    if state == "accepted":
        return x.get("by") or "owner"
    if state == "dismissed":
        return x.get("dismissed_by") or "owner"
    return "ergostat"


def supersede(p, spec: Spec, why: str = "the model changed since it was made") -> list[str]:
    """Every change still open that was made against a model version that has since changed: superseded."""
    v = ver.version(spec)
    out = []
    for pid, x in stored(p).items():
        if x["state"] in OPEN and x.get("version") and x["version"] != v and x.get("kind") not in ("process", "tuning"):
            event(p, pid, "superseded", {"why": why, "version_now": v})
            out.append(pid)
    return out


def current(x: dict, spec: Spec) -> bool:
    """A parameter proposal still changes the value written as it was when it was proposed (another
    proposal for the same parameter, accepted since, has made it stale)."""
    for n, was in (x.get("previous") or {}).items():
        prm = spec.parameters.get(n)
        if prm is None or (prm.value is None) != (was is None) or (was is not None and abs(prm.value - was) > 1e-12 * max(1.0, abs(was))):
            return False
    return True


def pending(p, spec: Spec | None = None) -> list[dict]:
    """The changes waiting (checked, under test, or passed), made against the model's version as it is now. A loop's
    process or gain is offered by its analysis (``review.control_pending``), not here."""
    spec = spec or p.model.spec
    v = ver.version(spec)
    return sorted((x for x in stored(p).values() if x["status"] == "pending" and x.get("kind") not in ("process", "tuning")
                   and x.get("version") == v and current(x, spec)), key=lambda x: x.get("created") or 0)


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


def make(p, snap: dict | None = None, n: int | None = None, which: str = "parts") -> list[dict]:
    """Estimate, then propose: every change the record supports, for the model as it is now, on the
    reference window (never the page's), by the calibration ``which`` asks for (``estimate.SCOPES``:
    each part alone, with the equations proposed for flows that have none; each system alone, driven by
    its measured inputs; the whole model). Pending proposals of the same calibration, or for an older
    structure, are let go; accepted and dismissed ones are kept. An estimate the record does not support
    is kept with why (``estimate.judged``), shown beside its parameter, and proposes nothing."""
    spec: Spec = p.model.spec
    data = ob.measured(p, ob.reference(p, (snap or {}).get("at"), n))
    estimates = es.estimate(p, snap, n, which)
    st = ver.structure(spec)
    base = sim.plan(spec)
    before = _total(spec, data, base)
    now = time.time()
    found: list[dict] = []
    groups: dict[tuple, list[str]] = {}
    for key, e in sorted(estimates.items()):            # parameters fitted together are proposed together
        name = e.get("parameter", key)
        prm = spec.parameters.get(name)
        if prm is None or not prm.estimate:
            continue
        e["refused"] = es.judged(e, prm.value)
        groups.setdefault((e.get("scope", "parts"), *sorted([name, *e.get("with", [])])), []).append(key)
    _keep_judgements(p, spec, estimates, which)
    for keys in groups.values():
        if any(estimates[k].get("value") is None for k in keys):
            continue
        e = estimates[keys[0]]
        scope = e.get("scope", "parts")
        sure_keys = [k for k in keys if estimates[k]["refused"] is None]
        if not sure_keys:
            continue
        name_of = {k: estimates[k].get("parameter", k) for k in keys}
        group = [name_of[k] for k in keys]
        sure = [name_of[k] for k in sure_keys]
        estimates_by = {name_of[k]: estimates[k] for k in keys}
        moved = {name_of[k]: float(ye.number(estimates[k]["value"])) for k in sure_keys}
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
        corr = [(a, b, c) for a in sure for b, c in (estimates_by[a].get("corr") or {}).items() if a < b and c is not None]
        objective = {"before": e["before"], "after": e["after"], "held_before": e.get("held_before"),
                     "held_after": e.get("held_after")}
        fall = 1 - e["after"] / e["before"] if e["before"] > 0 else None
        weights = ", ".join(f"{r} {ye.number(w)}" for r, w in sorted((e.get("weights") or {}).items()))
        held = (1 - e["held_after"] / e["held_before"] if e.get("held_before") and e.get("held_after") is not None else None)
        left = es.open_loops(spec) if scope == "whole" else []
        how = ({"parts": "",
                "whole": (f"calibrated on the model's replay, every stock integrated from its flows and what the decisions set "
                          f"taken as measured, so {es.open_said(left)} {'stay' if len(left) > 1 else 'stays'} open, "
                          if left else "calibrated on the whole model's replay (every stock integrated from its flows), ")}
               .get(scope, f"calibrated on {e.get('scope_words') or scope}, its stocks integrated from its flows, "))
        found.append({
            "id": _id("parameter", st, sorted(moved.items())) if scope == "parts" else _id("parameter", st, scope, sorted(moved.items())),
            "kind": "parameter", "scope": scope, "scope_words": e.get("scope_words") or es.SCOPE_WORDS["parts"],
            "target": ", ".join(f"parameter.{n}" for n in moved), "parameters": moved,
            "previous": {n: spec.parameters[n].value for n in moved},
            "uncertainty": {n: es.said_se(estimates_by[n], moved[n]) for n in moved},
            "parts": sorted({r for n in moved for r in users_of(spec, n)}), "touched": e.get("fitted_to", []),
            "title": "; ".join(f"{n}: {said(n, spec.parameters[n].value)} → {said(n, v, es.said_se(estimates_by[n], v))}"
                               for n, v in moved.items()),
            "reason": (f"{how}estimated {'together ' if len(group) > 1 else ''}from {e['n']} points over the last "
                       f"{series.dur(e['window'])}, the last fifth held out, by weighted least squares on "
                       f"{', '.join(e['fitted_to'])}: " +
                       (f"their weighted error falls by {fall:.0%} on the record fitted" if fall is not None else "it fits better") +
                       (f" and by {held:.0%} on the record held out" if held is not None else "") +
                       "".join(f"; {a} and {b} are correlated {c:+.2f}" for a, b, c in corr if abs(c) > 0.5) +
                       (f"; each series weighted by its spread ({weights})" if weights else "") +
                       (f" (±: one standard error; {', '.join(sorted(set(group) - set(sure)))} not proposed: "
                        f"{'; '.join(estimates_by[x]['refused'] for x in sorted(set(group) - set(sure)))})" if set(group) - set(sure)
                        else " (±: one standard error)")),
            "objective": objective,
            "estimate": {n: estimates_by[n] for n in group}, "fit_before": before, "fit_after": after,
            "edit": _joined(edits) if not errors else {"error": "; ".join(errors)}})
    if which == "parts":
        found += _equations(spec, data, before)
    props = stored(p)
    for k in [k for k, x in props.items() if x["status"] == "pending" and not candidate(x) and
              (x.get("structure") != st or _calibration(x) == which)]:
        del props[k]
    admit(p, spec, props, found, now, data.grid.until - data.grid.since)
    save(p, props)
    return pending(p, spec)


def admit(p, spec: Spec, props: dict, found: list[dict], now: float, window: float) -> None:
    """ergostat's own finders' changes, into ``props``: each not made already (dismissed, accepted or waiting), and
    not held back (``memory``: the same target turned away on this version while the record has not grown enough
    since, counted on the item turned away); refused at the gate (``gate``) when it worsens the fit of the whole
    model or near what it touches, with both numbers; else pending."""
    from . import gate as gt
    from . import memory as mem
    st, v = ver.structure(spec), ver.version(spec)
    for x in found:
        if x["id"] in props:                       # dismissed (or accepted) already: not made again
            continue
        x = {**x, "made_by": x.get("made_by") or "ergostat", "window": window}
        x["key"] = mem.key(x)
        h = mem.held(p, spec, x["key"], now)
        if h is not None:
            props[h["prior"]["id"]] = mem.repeat(p, h, x.get("title") or "", x.get("title") or "")
            continue
        refs = [*(x.get("parts") or []), *(x.get("touched") or []), *str(x.get("target") or "").split(", ")]
        g = gt.check(spec, x.get("fit_before"), x.pop("gate_fit", None) or x.get("fit_after"), [r for r in refs if r])
        x["gate"] = {"whole": g["whole"], "local": g["local"], "said": gt.summary(g)}
        x["neighbourhood"] = g["neighbourhood"]
        state = {"status": "pending"}
        if g["worse"]:
            fitted = _fitted_said(x)
            state = {"status": "refused", "state": "refused", "gated": True, "decided": now,
                     "why": f"it clearly worsens the fit: {g['worse']}" + (f", though {fitted}" if fitted else "")}
        props[x["id"]] = {**x, **state, "created": now, "structure": st, "version": v}


def _fitted_said(x: dict) -> str | None:
    """What the estimate itself improved, on what it was fitted to: the other number beside the gate's."""
    o = x.get("objective") or {}
    if not o.get("before"):
        return None
    on = ", ".join((next(iter((x.get("estimate") or {}).values()), {}) or {}).get("fitted_to") or []) or "what it was fitted to"
    return (f"fitted {x.get('scope_words') or 'each part alone'}, its weighted error on {on} falls by "
            f"{1 - o['after'] / o['before']:.0%} ({o['before']:.3g} → {o['after']:.3g})")


def _calibration(x: dict) -> str:
    """Which calibration made a proposal (``estimate.SCOPES``; a what-if is the owner's own)."""
    if x.get("kind") == "structure":
        return "structure"
    sc = x.get("scope", "parts")
    return "systems" if sc.startswith("system:") else sc


def _keep_judgements(p, spec: Spec, estimates: dict, which: str = "parts") -> None:
    f = es.path(p, ver.structure(spec), which)
    try:
        f.write_text(json.dumps(estimates, indent=1))
    except OSError:
        pass


def _value_edit(prm, value: float) -> ye.Edit:
    ye.own(prm.defined, f"parameter {prm.name}")
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
        pid = _id("equation", ver.structure(spec), f.name, text)
        try:
            edit = _equation_edit(spec, f, text, params, pid)
        except ye.EditError as err:
            edit = {"error": str(err)}
        inside = [c for c in causes if c != own and target in loops and c in loops]
        out.append({
            "id": pid, "kind": "equation", "target": target, "parts": [target],
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


def _equation_edit(spec: Spec, f, text: str, params: dict, pid: str) -> dict:
    """The equation written on its flow, and each parameter it adds, marked ``inferred:`` with this change's item."""
    if f.defined is None:
        raise ye.EditError(f"flow {f.name}: where it is written is not known")
    ye.own(f.defined, f"flow {f.name}")
    path = f.defined.file
    first = ye.add_key(path, f.defined.line, "equation", text)
    entries = []
    for nm, (v, u) in params.items():
        value = ye.duration(v) if u == "h" else ye.number(v)          # a time, written as one (read in hours)
        entries.append([f"  {nm}:", f"    value: {value}"] + ([f"    unit: {u}"] if u and u != "h" else []) +
                       ["    estimate: true          # fitted by least squares; refitted as the record grows",
                        f"    inferred: {item_of(pid)}"])
    second = ye.add_entries(path, "parameters", entries)
    return _joined([first, second])


def is_time(prm) -> bool:
    """A parameter that is a time: written as a duration, or in hours."""
    return bool(prm.duration) or (prm.unit or "").strip() in ("h", "hour", "hours")


def parse_value(prm, raw) -> float:
    """A value the owner typed for a parameter: a number in its unit; for a time written as a duration, a
    duration with its unit (``20s``, ``5m``, ``2h``: a bare number is refused, since the panel shows it in
    seconds and the model counts hours). A time is above 0 unless its range says it may be less."""
    import re

    from ..durations import UNITS
    text = str(raw).strip().replace("\u2212", "-")
    m = re.fullmatch(r"([+-]?)\s*(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)\s*(ms|s|m|h|d|w)?", text)
    if not m:
        raise ProposalError(f"parameter {prm.name}: {text!r} is not a number{' or a duration' if prm.duration else ''}")
    v = float(m.group(2)) * (-1 if m.group(1) == "-" else 1)
    if m.group(3):
        if not is_time(prm):
            raise ProposalError(f"parameter {prm.name}: {text!r} is a duration, and {prm.name} is not a time"
                                f"{f' (its unit is {prm.unit})' if prm.unit else ''}: write a number")
        v *= UNITS[m.group(3)] / 3600.0
    elif prm.duration:
        raise ProposalError(f"parameter {prm.name} is a duration: write it with its unit, like {m.group(2)}s, {m.group(2)}m "
                            f"or {m.group(2)}h")
    if not math.isfinite(v):
        raise ProposalError(f"parameter {prm.name}: {text!r} is not a number")
    if is_time(prm) and v <= 0 and not (prm.range and prm.range[0] < 0):
        raise ProposalError(f"parameter {prm.name} is a time: it must be more than 0 (its range would have to say it may be less)")
    return v


def what_if(spec: Spec, raw: dict[str, str]) -> dict[str, float]:
    """The values a what-if tries, checked: each names a parameter with a value (not a lookup)."""
    out = {}
    for name, v in raw.items():
        prm = spec.parameters.get(name)
        if prm is None or prm.table:
            raise ProposalError(f"no parameter {name} with a value to try")
        out[name] = parse_value(prm, v)
    return out


def _said_value(prm, x) -> str:
    if x is None:
        return "no value"
    return ye.duration(x) if prm.duration else f"{ye.number(x)}{' ' + prm.unit if prm.unit else ''}"


def faults_said(faults: dict[str, dict[str, int]]) -> list[str]:
    """A run's equation faults, in words: each part, what it did and how often (each was taken as 0)."""
    from .extremes import FAULT_WORDS
    out = []
    for r, got in sorted(faults.items()):
        said = "; ".join(f"{FAULT_WORDS.get(w, w)} {n} time" + ("s" if n > 1 else "") for w, n in sorted(got.items()))
        out.append(f"{r} {said}")
    return out


def judge_what_if(p, spec: Spec, moved: dict[str, float], data: ob.Data | None = None, extremes: bool = True) -> dict:
    """What a what-if does to the model before it is proposed (Sterman ch. 21, parameter assessment and the
    extreme-conditions test): the fit before and after on the reference window, per stock and its payoff;
    what refuses it (a run that blows up, an equation that faults where the model as written does not); and
    what is said with it (a value outside the parameter's range, an extreme condition the model as written
    passes and this one fails)."""
    from . import extremes as ex
    base_pl, pl = sim.plan(spec), sim.plan(spec, moved)
    base_run, run = sim.replay(spec, data, base_pl), sim.replay(spec, data, pl)
    refused, warnings = [], []
    if not run.valid:
        refused.append(f"with it the replay blows up ({'; '.join(run.invalid)})")
    new = {r: {w: n for w, n in got.items() if n > (base_run.faults.get(r) or {}).get(w, 0)} for r, got in run.faults.items()}
    new = {r: got for r, got in new.items() if got}
    if new:
        refused.append(f"with it {'; '.join(faults_said(new))}, each taken as 0: a value the model cannot run")
    for n, v in moved.items():
        prm = spec.parameters[n]
        if prm.value is not None and abs(v - prm.value) <= 1e-12 * max(1.0, abs(prm.value)):
            refused.append(f"{n} is {_said_value(prm, v)} already")
        if prm.range and not prm.range[0] <= v <= prm.range[1]:
            warnings.append(f"{n} {_said_value(prm, v)} is outside its range ({_said_value(prm, prm.range[0])} to "
                            f"{_said_value(prm, prm.range[1])}): what the model says it might be")
    if extremes and not refused:
        scales = ex.scales_of(data, spec)
        was, now = ex.failures(spec, None, scales), ex.failures(spec, moved, scales)
        for (ref, what), x in sorted(now.items()):
            if (ref, what) not in was:
                warnings.append("it fails an extreme-conditions test the model as written passes: " + ex.message(spec, pl, ref, what, x))
    before = _total(spec, data, base_pl)
    after = _total(spec, data, pl) if run.valid else {"total": None, "stocks": {}, "equations": {}}
    return {"refused": refused, "warnings": warnings, "fit_before": before, "fit_after": after,
            "window": data.grid.until - data.grid.since}


def whatif_fit(p, raw: dict[str, str], snap: dict | None = None, n: int | None = None) -> dict:
    """A what-if's fit, shown beside the charts before anything is stored: the payoff and each stock's fit
    before and after on the reference window, and what would refuse it or be said with it."""
    spec: Spec = p.model.spec
    moved = what_if(spec, raw)
    data = ob.measured(p, ob.reference(p, (snap or {}).get("at"), n))
    got = judge_what_if(p, spec, moved, data, extremes=False)
    touched = sorted({r for k in moved for u in users_of(spec, k) for r in (u, *_stocks_of(spec, u))})
    return {**got, "parameters": moved, "touched": touched}


def propose_value(p, name: str, raw, snap: dict | None = None, n: int | None = None) -> dict:
    """One what-if value made a proposal (``propose_values``)."""
    return propose_values(p, {name: raw}, snap, n)


def propose_values(p, raw: dict[str, str], snap: dict | None = None, n: int | None = None) -> dict:
    """The owner's own what-if, made one proposal for every value tried together (what the charts drew):
    with the fit before and after on the reference window and its edit. Refused when the values make the
    model fault or blow up, or are what is written already; a value outside its range, or one that fails an
    extreme condition the model passes, is said in its reason. Like any proposal it changes nothing until
    accepted. An accepted what-if is never overwritten: asking again makes another."""
    spec: Spec = p.model.spec
    if not raw:
        raise ProposalError("no value to propose")
    moved = what_if(spec, raw)
    data = ob.measured(p, ob.reference(p, (snap or {}).get("at"), n))
    judged = judge_what_if(p, spec, moved, data)
    if judged["refused"]:
        raise ProposalError("not proposed: " + "; ".join(judged["refused"]))
    st, v = ver.structure(spec), ver.version(spec)
    try:
        edit = _joined([_value_edit(spec.parameters[k], x) for k, x in moved.items()])
    except ye.EditError as err:
        edit = {"error": str(err)}
    before, after = judged["fit_before"], judged["fit_after"]
    b, a = before.get("total") or {}, after.get("total") or {}
    props = stored(p)
    pid = _id("parameter", st, "what-if", sorted(moved.items()))
    if (props.get(pid) or {}).get("status") == "accepted":
        pid = _id("parameter", st, "what-if", sorted(moved.items()), time.time())
    names = sorted(moved)
    parts = sorted({u for k in names for u in users_of(spec, k)})
    x = {"id": pid, "kind": "parameter", "scope": "what-if", "scope_words": "the owner's what-if",
         "target": ", ".join(f"parameter.{k}" for k in names), "parameters": moved,
         "previous": {k: spec.parameters[k].value for k in names}, "uncertainty": dict.fromkeys(names),
         "parts": parts, "touched": sorted({r for u in parts for r in (u, *_stocks_of(spec, u))}),
         "title": "; ".join(f"{k}: {_said_value(spec.parameters[k], spec.parameters[k].value)} → "
                            f"{_said_value(spec.parameters[k], moved[k])}" for k in names),
         "reason": ("tried by the owner as a what-if, not estimated" +
                    (" (the values together, as the charts drew them)" if len(names) > 1 else "") +
                    ": " + (f"the model's scaled error on the last {series.dur(judged['window'])} of record goes from "
                            f"{_sig(b.get('nmse'))} to {_sig(a.get('nmse'))} (lower is better)" if b or a
                            else "nothing it moves is fitted yet") +
                    "".join(f"; {w}" for w in judged["warnings"])),
         "warnings": judged["warnings"],
         "fit_before": before, "fit_after": after, "edit": edit,
         "status": "pending", "created": time.time(), "structure": st, "version": v,
         "window": judged["window"]}
    props[pid] = x                                  # the owner asked again: proposed again, even if let go before
    save(p, props)
    return x


def _sig(x) -> str:
    return "–" if x is None else f"{x:.3g}"


def _two(x) -> str:
    return "–" if x is None else f"{x:.2f}"


def _stocks_of(spec: Spec, ref: str) -> list[str]:
    kind, _, name = ref.partition(".")
    f = spec.flows.get(name) if kind == "flow" else None
    return [f"stock.{s}" for s in (f.source, f.target) if s] if f else []


def find(p, pid: str) -> dict:
    props = stored(p)
    hits = [x for k, x in props.items() if k.startswith(pid)] if pid else []
    if len(hits) != 1:
        raise ProposalError(f"no proposal {pid}" if not hits else f"{pid} is the start of {len(hits)} proposals: give more of it")
    return hits[0]


def dismiss(p, pid: str, reason: str | None = None) -> dict:
    """Let a proposal go, with the owner's reason when they give one: kept, so the same change is not
    proposed again (a changed one, another value or another edit, is a new proposal)."""
    props = stored(p)
    x = find(p, pid)
    if x["status"] != "pending":
        raise ProposalError(f"proposal {x['id']} is {x['status']} already")
    x["status"], x["decided"] = "dismissed", time.time()
    if reason:
        x["dismissed_because"] = reason.strip()[:500]
    x["dismissed_by"] = "owner"
    props[x["id"]] = x
    save(p, props)                                  # ergostat.model-change.dismissed, from the owner, with the reason
    return x


def accept(p, pid: str, snap: dict, by: str = "owner", expect: str | None = None, why: str | None = None,
           policy: str | None = None) -> dict:
    """Apply the proposal's edit, check the model still compiles (else put the file back), record the
    change with the fit before and after, and return what was done. ``expect`` is the hash of the diff the
    owner was shown (``review.diff_of``): refused unless what would be written is exactly that."""
    from .. import model as mdl
    from ..spec import read
    props = stored(p)
    x = find(p, pid)
    if x["status"] != "pending":
        raise ProposalError(f"proposal {x['id']} is {x['status']} already")
    if "error" in (x.get("edit") or {"error": "none"}):
        raise ProposalError(f"its edit cannot be made by ergostat ({(x.get('edit') or {}).get('error')}); write it by hand")
    if x["structure"] != ver.structure(p.model.spec) or (x.get("version") and x["version"] != ver.version(p.model.spec)):
        raise ProposalError("the model has changed since it was proposed: ask for proposals again")
    if not current(x, p.model.spec):
        raise ProposalError("the value it changes has been changed since it was proposed: ask for proposals again")
    edits = [ye.Edit.from_dict(d) for d in x["edit"]["files"]]
    old_text = {e.file: Path(e.file).read_text(encoding="utf-8") for e in edits}
    _, _, fit_before = ft.compute(p, snap)
    v_before = ver.version(p.model.spec)
    try:
        new_text = ye.apply_together(edits)                       # every file checked before any is written
    except ye.EditError as e:
        raise ProposalError(str(e)) from None
    if expect is not None:
        from .review import diff_of
        shown = diff_of(x, p.model.path.parent)
        if shown.get("hash") != expect:
            raise ProposalError("the files have changed since the diff was shown: look at it again before accepting")
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
    x["status"], x["state"], x["decided"], x["by"] = "accepted", "accepted", time.time(), by
    x["applied"] = {"version_before": v_before, "version_after": ver.version(p.model.spec),
                    "fit_before": ft._slim(fit_before["total"]), "fit_after": ft._slim(fit_after["total"])}
    if why:
        x["applied"]["why"] = why
    if policy:
        x["applied"]["policy"] = policy
    props[x["id"]] = x
    save(p, props)                                  # ergostat.model-change.accepted, from whoever decided
    written(p, x, by)
    supersede(p, p.model.spec)                      # what was made against the version before is made again, or not
    return x


def written(p, x: dict, by: str) -> dict:
    """``ergostat.model.changed``: an accepted edit written, with its diff, the model's version before and after and
    the fit before and after: the model's history."""
    return p.events.add("ergostat.model.changed", item=p.model.name, source="ergostat",
                        data={"change": x["id"], "item": item_of(x["id"]), "kind": x["kind"], "title": x["title"],
                              "target": x.get("target"), "reason": x.get("reason"), "accepted_by": by,
                              **({"made_by": x["made_by"]} if x.get("made_by") else {}),
                              "diff": x["edit"]["diff"], **x.get("applied", {})})


def accepted(p, since: float | None = None) -> list[dict]:
    """The changes accepted, oldest first: the model's history of what the record taught it."""
    return [{"time": e["time"], "proposal": e["data"].get("change"), **e["data"]}
            for e in p.events.query(n=None, type="ergostat.model.changed", since=since)]
