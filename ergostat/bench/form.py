"""A model as plain data, and back to YAML in one canonical style, so a defect or a stand-in's change is made on the
model's parts, never on its text, and written back the same way every time.

``of_spec`` reads a compiled model into ``{"name", "description", "parameters", "stocks", "flows", "auxiliaries"}``;
``render`` writes it as one ``ergostat.yaml``; ``hunks`` is the smallest edit from one text to another, in the review
queue's form. Driven-by entries are written ``+stock.x``, or ``{cause: +flow.y, instant: true}``."""

from __future__ import annotations

import copy
import difflib
import json
import re

from ..numbers import yamledit as ye
from ..spec import equation as eq
from ..spec.ir import Spec

PLAIN = re.compile(r"^[A-Za-z0-9_./ ()*+-]*$")


def _driven(x) -> list:
    out = []
    for r in x.driven_by:
        s = str(r)
        sign = x.polarity.get(s)
        cause = ("+" if sign and sign > 0 else "-" if sign else "") + s
        out.append({"cause": cause, "instant": True} if s in x.instant else cause)
    return out


def of_spec(spec: Spec) -> dict:
    m = {"name": spec.name, "parameters": {}, "stocks": {}, "flows": {}, "auxiliaries": {}}
    for n, q in spec.parameters.items():
        m["parameters"][n] = {"value": q.value, "unit": q.unit, "estimate": q.estimate, "description": q.description}
    for n, s in spec.stocks.items():
        m["stocks"][n] = {"unit": s.unit, "description": s.description, "initial": s.initial, "sensor": bool(s.sensors)}
    for n, f in spec.flows.items():
        m["flows"][n] = {"from": f.source, "to": f.target, "two_way": f.two_way, "driven_by": _driven(f),
                         "equation": f.equation.text if f.equation else None, "sensor": bool(f.sensors),
                         "description": f.description}
    for n, a in spec.auxiliaries.items():
        m["auxiliaries"][n] = {"unit": a.unit, "exogenous": a.exogenous, "driven_by": _driven(a),
                               "equation": a.equation.text if a.equation else None, "sensor": bool(a.sensors),
                               "description": a.description}
    return m


def copy_of(m: dict) -> dict:
    return copy.deepcopy(m)


def _s(v) -> str:
    v = str(v)
    return v if v and PLAIN.match(v) and v[0] not in "-*(" and not v.strip().isdigit() and v == v.strip() else json.dumps(v)


def _cause(c) -> str:
    return f"{{cause: {c['cause']}, instant: true}}" if isinstance(c, dict) else c


def render(m: dict) -> str:
    out = [f"# {m['description']}"] if m.get("description") else []
    out.append(f"name: {m['name']}")
    if m["parameters"]:
        out.append("parameters:")
        for n, q in m["parameters"].items():
            out.append(f"  {n}:")
            if q.get("value") is not None:
                out.append(f"    value: {ye.number(q['value'])}")
            if q.get("unit"):
                out.append(f"    unit: {_s(q['unit'])}")
            if q.get("estimate"):
                out.append("    estimate: true")
            if q.get("description"):
                out.append(f"    description: {_s(q['description'])}")
    for section in ("stocks", "auxiliaries", "flows"):
        if not m[section]:
            continue
        out.append(f"{section}:")
        for n, x in m[section].items():
            out.append(f"  {n}:")
            if section == "flows":
                if x.get("from"):
                    out.append(f"    from: {x['from']}")
                if x.get("to"):
                    out.append(f"    to: {x['to']}")
                if x.get("two_way"):
                    out.append("    two-way: true")
            if x.get("unit"):
                out.append(f"    unit: {_s(x['unit'])}")
            if x.get("exogenous"):
                out.append("    exogenous: true")
            if x.get("initial") is not None:
                out.append(f"    initial: {ye.number(x['initial'])}")
            if x.get("description"):
                out.append(f"    description: {_s(x['description'])}")
            if x.get("driven_by"):
                out.append(f"    driven-by: [{', '.join(_cause(c) for c in x['driven_by'])}]")
            if x.get("equation"):
                out.append(f"    equation: {_s(x['equation'])}")
            if x.get("sensor"):
                out += ["    sensor:", "      manual: true"]
    return "\n".join(out) + "\n"


def hunks(old: str, new: str) -> list[dict]:
    """The smallest edit from ``old`` to ``new``, as the review queue writes hunks: ``{line, old, new}``."""
    a, b = old.rstrip("\n").split("\n"), new.rstrip("\n").split("\n")
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append({"line": i1 + 1, "old": a[i1:i2], "new": b[j1:j2]})
    return out


# ---- equations as sums of terms (for a sign flipped, a term dropped or added)

def terms(text: str) -> list[tuple[int, tuple]]:
    """An equation's top-level terms, each with its sign: ``a - k * b`` is [(+1, a), (-1, k * b)]."""
    def go(n, sign):
        if n[0] == "bin" and n[1] in "+-":
            return go(n[2], sign) + go(n[3], sign if n[1] == "+" else -sign)
        if n[0] == "neg":
            return go(n[1], -sign)
        return [(sign, n)]
    return go(eq.parse(text), 1)


def of_terms(ts: list[tuple[int, tuple]]) -> str:
    if not ts:
        return "0"
    tree = ts[0][1] if ts[0][0] > 0 else ("neg", ts[0][1])
    for sign, t in ts[1:]:
        tree = ("bin", "+" if sign > 0 else "-", tree, t)
    return eq.text(tree)


def refs_of(tree) -> set[str]:
    return set(eq.refs(tree))


def params_of(tree) -> set[str]:
    return {n[1] for n in eq.walk(tree) if n[0] == "par"}


def used_parameters(m: dict) -> set[str]:
    out: set[str] = set()
    for section in ("flows", "auxiliaries"):
        for x in m[section].values():
            if x.get("equation"):
                out |= params_of(eq.parse(x["equation"]))
    return out


def drop_unused(m: dict) -> None:
    used = used_parameters(m)
    for n in [n for n in m["parameters"] if n not in used]:
        del m["parameters"][n]


def tidy_causes(x: dict) -> None:
    """A part's driven-by kept to what its equation names (with their signs as written), so ``check`` does not find
    a cause the equation ignores. The sign of a cause the equation names in one term only follows that term's."""
    if not x.get("equation"):
        return
    ts = terms(x["equation"])
    named = {}
    for sign, t in ts:
        for r in refs_of(t):
            named.setdefault(r, set()).add(sign)
    keep = []
    for c in x.get("driven_by") or []:
        s = c["cause"] if isinstance(c, dict) else c
        ref = s.lstrip("+-")
        if ref not in named:
            continue
        keep.append(c)
    have = {(c["cause"] if isinstance(c, dict) else c).lstrip("+-") for c in keep}
    for r, signs in named.items():
        if r not in have:
            keep.append(("+" if signs == {1} else "-" if signs == {-1} else "") + r)
    x["driven_by"] = keep


def free_name(m: dict, want: str) -> str:
    taken = set(m["parameters"]) | set(m["stocks"]) | set(m["flows"]) | set(m["auxiliaries"])
    if want not in taken:
        return want
    i = 2
    while f"{want}-{i}" in taken:
        i += 1
    return f"{want}-{i}"
