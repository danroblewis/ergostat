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


def changed_sensors(before: Spec, after: Spec) -> list[str]:
    """The parts whose sensors a change alters (``stock.x``)."""
    out = []
    for kind, a, b in (("stock", before.stocks, after.stocks), ("flow", before.flows, after.flows),
                       ("auxiliary", before.auxiliaries, after.auxiliaries)):
        for n in sorted(set(a) & set(b)):
            if _hash(_plain(a[n].sensors)) != _hash(_plain(b[n].sensors)):
                out.append(f"{kind}.{n}")
    return out
