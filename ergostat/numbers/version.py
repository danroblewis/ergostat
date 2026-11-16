"""A model's version, as a short hash. The **structure** is what the model says moves what: its
stocks, its flows and what they connect, its auxiliaries, every driven-by and equation, and the
parameters' names and units. The **version** is the structure with the numbers written in it (each
parameter's value, a declared rate). An estimate belongs to a structure (it is the number that
structure fits best); a fit belongs to a version (it is how well those numbers do)."""

from __future__ import annotations

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
    return _hash([_structure(spec), numbers])
