"""A model's version, as a short hash. The **structure** is what the model says moves what: its
stocks, its flows and what they connect, its auxiliaries, every driven-by and equation, and the
parameters' names and units. The **version** is the structure with the numbers written in it (each
parameter's value, a declared rate). An estimate belongs to a structure (it is the number that
structure fits best); a fit belongs to a version (it is how well those numbers do).

Beside them, the parts of the spec the dynamics model is not: the **control** (the goals, the blocks, the judge
among them, and the agents that fill them) and the **measurement** (the sensors of the parts already there; a part
added with its sensor is structure). A change to either is not a parameter change whatever it leaves of the
structure (``improve.kind_of``)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re

from ..spec.ir import Spec


def _structure(spec: Spec) -> dict:
    def links(x):
        return sorted(f"{x.polarity.get(str(r), 0):+d}{r}" for r in x.driven_by)
    return {
        "stocks": sorted(spec.stocks),
        "flows": {n: [f.source, f.target, links(f), f.equation.text if f.equation else None, f.two_way]
                  for n, f in sorted(spec.flows.items())},
        "auxiliaries": {n: [links(a), a.equation.text if a.equation else None, a.exogenous]
                        for n, a in sorted(spec.auxiliaries.items())},
        "parameters": {n: [p.unit, bool(p.table), p.estimate] for n, p in sorted(spec.parameters.items())},
    }


def _hash(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:10]


def structure(spec: Spec) -> str:
    return _hash(_structure(spec))


def _numbers(spec: Spec) -> dict:
    numbers = {"parameters": {n: [p.value, p.table] for n, p in sorted(spec.parameters.items())},
               "rates": {n: f.rate for n, f in sorted(spec.flows.items()) if f.rate is not None}}
    ranges = {n: list(p.range) for n, p in sorted(spec.parameters.items()) if p.range}
    if ranges:
        numbers["ranges"] = ranges
    return numbers


def values(spec: Spec) -> str:
    """The numbers written in the model (each parameter's value and table, a declared rate, a range), hashed."""
    return _hash(_numbers(spec))


def version(spec: Spec) -> str:
    numbers = {"parameters": {n: [p.value, p.table] for n, p in sorted(spec.parameters.items())},
               "rates": {n: f.rate for n, f in sorted(spec.flows.items()) if f.rate is not None}}
    ranges = {n: list(p.range) for n, p in sorted(spec.parameters.items()) if p.range}
    if ranges:                                          # only where written, so a model without one keeps its version
        numbers["ranges"] = ranges
    return _hash([_structure(spec), numbers])


PLACES = ("where", "defined", "value_at", "description")     # where a thing is written, and its words: not what it is


def _plain(x, depth: int = 0):
    """What a part of the spec is, as plain data: a dataclass by its fields (leaving out where it is written and its
    description, so an edit elsewhere in the file never changes it), containers by their items, the rest as text."""
    if depth > 12:
        return None
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        if type(x).__name__ == "Where":
            return None
        return {f.name: _plain(getattr(x, f.name), depth + 1) for f in dataclasses.fields(x) if f.name not in PLACES}
    if isinstance(x, dict):
        return {str(k): _plain(v, depth + 1) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, list | tuple):
        return [_plain(v, depth + 1) for v in x]
    if isinstance(x, set | frozenset):
        return sorted(str(v) for v in x)
    if x is None or isinstance(x, bool | int | float | str):
        return x
    text = str(x)
    return type(x).__name__ if " at 0x" in text else text


def control(spec: Spec) -> str:
    """The goals, the blocks and the agents (the judge's policy among its block's keys), hashed: what decides, not
    what moves."""
    return _hash(_plain({"goals": spec.goals, "blocks": {n: b for n, b in spec.blocks.items() if not b.implied},
                         "agents": spec.agents}))


def changed_control(before: Spec, after: Spec) -> list[str]:
    """The goals, blocks and agents a change alters, adds or removes (``goal.x``, ``block.y``, ``agent.z``)."""
    out = []
    for kind, a, b in (("goal", before.goals, after.goals), ("block", before.blocks, after.blocks),
                       ("agent", before.agents, after.agents)):
        for n in sorted(set(a) | set(b)):
            if _hash(_plain(a.get(n))) != _hash(_plain(b.get(n))):
                out.append(f"{kind}.{n}")
    return out


def whole(spec: Spec) -> str:
    """The whole model's version: the dynamics (``version``), the control and the measurement together. What a run
    records it ran under: a change to any of them is a new model for the runs that start after it."""
    sensors = {kind: {n: x.sensors for n, x in sorted(t.items())}
               for kind, t in (("stocks", spec.stocks), ("flows", spec.flows), ("auxiliaries", spec.auxiliaries))}
    return _hash([version(spec), control(spec), _hash(_plain(sensors))])


def changed_sensors(before: Spec, after: Spec) -> list[str]:
    """The parts whose sensors a change alters (``stock.x``)."""
    out = []
    for kind, a, b in (("stock", before.stocks, after.stocks), ("flow", before.flows, after.flows),
                       ("auxiliary", before.auxiliaries, after.auxiliaries)):
        for n in sorted(set(a) & set(b)):
            if _hash(_plain(a[n].sensors)) != _hash(_plain(b[n].sensors)):
                out.append(f"{kind}.{n}")
    return out


# ---- the words and the units: what a reader is told, not what moves (a change to them alone is a wording change)

def _described(spec: Spec) -> dict:
    out: dict = {}
    for kind, t in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries),
                    ("parameter", spec.parameters), ("goal", spec.goals), ("block", spec.blocks), ("agent", spec.agents),
                    ("items", spec.items)):
        for n, x in t.items():
            out[f"{kind}.{n}"] = (getattr(x, "description", "") or "").strip()
            for s in (getattr(x, "sensors", None) or {}).values():
                out[f"{kind}.{n}.{s.name}"] = (s.description or "").strip()
    for n, d in spec.systems.items():
        out[f"system.{n}"] = (d or "").strip()
    return out


def words(spec: Spec) -> str:
    """Every part's description (and its sensors'), hashed: what the diagrams say of each when a reader clicks it."""
    return _hash(_described(spec))


def changed_words(before: Spec, after: Spec) -> list[str]:
    """The parts whose description a change alters (``stock.x``; a sensor's as ``stock.x.main``)."""
    a, b = _described(before), _described(after)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k in a and k in b)


def _units(spec: Spec) -> dict:
    return {f"{k}.{n}": (x.unit or "").strip() for k, t in (("stock", spec.stocks), ("flow", spec.flows),
                                                            ("auxiliary", spec.auxiliaries), ("parameter", spec.parameters))
            for n, x in t.items()}


def units(spec: Spec) -> str:
    return _hash(_units(spec))


def changed_units(before: Spec, after: Spec) -> list[str]:
    a, b = _units(before), _units(after)
    return sorted(k for k in set(a) & set(b) if a[k] != b[k])


def structure_but_units(spec: Spec) -> str:
    """The structure with the parameters' units left out: a change to a unit alone leaves it as it is."""
    s = _structure(spec)
    s["parameters"] = {n: v[1:] for n, v in s["parameters"].items()}
    return _hash(s)


def _kinds(spec: Spec) -> dict:
    return {n: {"id": k.id, "states": list(k.states), "on": dict(k.on)}
            for n, k in sorted(spec.items.items()) if not n.startswith("ergostat.")}


def items(spec: Spec) -> str:
    """The item kinds: their ids, states and the events that move them."""
    return _hash(_kinds(spec))


def renamed_parts(before: Spec, after: Spec) -> dict[str, str] | None:
    """The parts a change renames (``{"stock.old": "stock.new"}``): each new part says ``formerly:`` its old name, and
    the model is the same but for the names: its structure, its control, every sensor (what each part reads), every
    number (parameters' values and tables, declared rates) and every item kind (states and the events that move them).
    None when it is not a rename."""
    out: dict[str, str] = {}
    for kind, a, b in (("stock", before.stocks, after.stocks), ("flow", before.flows, after.flows),
                       ("auxiliary", before.auxiliaries, after.auxiliaries)):
        gone, new = set(a) - set(b), set(b) - set(a)
        for n in new:
            was = getattr(b[n], "formerly", None) or []
            hit = [w for w in was if w in gone]
            if len(hit) == 1:
                out[f"{kind}.{hit[0]}"] = f"{kind}.{n}"
        if len(gone) != sum(1 for k in out if k.startswith(kind + ".")) or \
                len(new) != sum(1 for v in out.values() if v.startswith(kind + ".")):
            return None
    if not out:
        return None

    def norm(x):
        if isinstance(x, dict):
            return {k: norm(v) for k, v in x.items()}
        if isinstance(x, list):
            xs = [norm(v) for v in x]
            return sorted(xs) if all(isinstance(v, str) for v in xs) else xs
        return x

    def renamed(x) -> object:
        text = json.dumps(x, sort_keys=True, default=str)
        for old, new in out.items():
            o, w = old.split(".", 1)[1], new.split(".", 1)[1]
            text = re.sub(rf'(?<![\w-]){re.escape(o)}(?![\w-])', w, text)
        return norm(json.loads(text))

    def plain(x) -> object:
        return norm(json.loads(json.dumps(x, sort_keys=True, default=str)))

    def control_of(s: Spec) -> dict:
        return _plain({"goals": s.goals, "blocks": {n: b for n, b in s.blocks.items() if not b.implied}, "agents": s.agents})

    def sensors_of(s: Spec) -> dict:                 # what each part reads, under the part's name: a rename keeps it
        return {f"{k}.{n}": _plain(x.sensors) for k, t in (("stock", s.stocks), ("flow", s.flows),
                                                           ("auxiliary", s.auxiliaries)) for n, x in t.items()}
    same = all(renamed(f(before)) == plain(f(after)) for f in (_structure, control_of, sensors_of, _numbers, _kinds))
    return out if same else None
