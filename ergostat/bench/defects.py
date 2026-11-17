"""The defect catalogue: known damage planted in a true model, each with the stocks it shows at (its locus), so the
benchmark can say whether it was fixed.

| Kind | What is planted | Parameters |
|---|---|---|
| ``flow-removed`` | a flow taken out (its causes and the parameters only it used with it) | ``flow`` |
| ``sign-flipped`` | a term of a flow's equation added where it was subtracted, or the reverse | ``flow``, ``term`` |
| ``parameter-x3`` | a parameter's value three times what it is (or ``factor``) | ``parameter``, ``factor`` |
| ``delay-missing`` | a flow's DELAY3 (or DELAY1, SMOOTH) taken away: it moves at once | ``flow`` |
| ``stock-merged`` | a stock between two flows merged away: its inflow goes straight on, its outflow is gone | ``stock`` |
| ``spurious-link`` | a cause that is not one: a term ``k * cause`` added to a flow, half its usual size | ``flow``, ``cause``, ``share`` |

The locus is the measured stocks the damage shows at: the ends of the flows it touches, followed through a hidden
stock to the measured ones beyond."""

from __future__ import annotations

from ..numbers import yamledit as ye
from ..spec import equation as eq
from . import form as fm

KINDS = ("flow-removed", "sign-flipped", "parameter-x3", "delay-missing", "stock-merged", "spurious-link")
DELAYS = ("DELAY1", "DELAY3", "SMOOTH", "SMOOTH3")


class DefectError(Exception):
    pass


def _ends(m: dict, truth: dict, flows: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(s):
        if s is None or s in seen:
            return
        seen.add(s)
        st = truth["stocks"].get(s)
        if st is None:
            return
        if st.get("sensor"):
            out.append(s)
            return
        for f in truth["flows"].values():           # hidden: on to the measured stocks beyond it
            if f["from"] == s:
                add(f["to"])
            if f["to"] == s:
                add(f["from"])
    for n in flows:
        f = truth["flows"].get(n) or m["flows"].get(n)
        if f:
            add(f["from"])
            add(f["to"])
    return out


def _flow(m: dict, name: str) -> dict:
    if name not in m["flows"]:
        raise DefectError(f"no flow {name}")
    return m["flows"][name]


def _uses(m: dict, ref: str) -> list[str]:
    return [n for sec in ("flows", "auxiliaries") for n, x in m[sec].items()
            if x.get("equation") and ref in fm.refs_of(eq.parse(x["equation"]))]


def _drop_cause(m: dict, ref: str) -> None:
    for sec in ("flows", "auxiliaries"):
        for x in m[sec].values():
            x["driven_by"] = [c for c in x.get("driven_by") or [] if (c["cause"] if isinstance(c, dict) else c).lstrip("+-") != ref]


def plant(m: dict, truth: dict, d: dict, record=None) -> dict:
    """Plant defect ``d`` in model ``m`` (changed in place); what was planted, and its locus."""
    k = d["kind"]
    if k == "parameter-x3":
        p = d["parameter"]
        if p not in m["parameters"]:
            raise DefectError(f"no parameter {p}")
        f = float(d.get("factor") or 3.0)
        was = m["parameters"][p]["value"]
        m["parameters"][p]["value"] = float(ye.number(was * f))
        users = [n for n in m["flows"] if m["flows"][n].get("equation") and p in fm.params_of(eq.parse(m["flows"][n]["equation"]))]
        says = f"parameter {p} is {ye.number(was * f)}, {'three times' if f == 3 else f'{f:.3g} times'} its true {ye.number(was)}"
        return {**d, "says": says, "locus": _ends(m, truth, users), "flows": users}
    if k == "flow-removed":
        f = d["flow"]
        _flow(m, f)
        if _uses(m, f"flow.{f}"):
            raise DefectError(f"flow {f} is named by {', '.join(_uses(m, f'flow.{f}'))}")
        locus = _ends(m, truth, [f])
        del m["flows"][f]
        _drop_cause(m, f"flow.{f}")
        fm.drop_unused(m)
        return {**d, "says": f"flow {f} is missing", "locus": locus, "flows": [f]}
    if k == "sign-flipped":
        x = _flow(m, d["flow"])
        ts = fm.terms(x["equation"])
        if len(ts) < 2:
            raise DefectError(f"flow {d['flow']}: one term, no sign between terms to flip")
        i = int(d.get("term", -1)) % len(ts)
        others = set().union(*(fm.refs_of(t) for j, (_, t) in enumerate(ts) if j != i))
        mine = fm.refs_of(ts[i][1]) - others
        ts[i] = (-ts[i][0], ts[i][1])
        x["equation"] = fm.of_terms(ts)
        new = []
        for c in x.get("driven_by") or []:
            s = c["cause"] if isinstance(c, dict) else c
            if s.lstrip("+-") in mine and s[:1] in "+-":
                s = ("-" if s[0] == "+" else "+") + s[1:]
            new.append({**c, "cause": s} if isinstance(c, dict) else s)
        x["driven_by"] = new
        return {**d, "says": f"flow {d['flow']}: the sign of a term is flipped ({x['equation']})", "locus": _ends(m, truth, [d["flow"]]),
                "flows": [d["flow"]]}
    if k == "delay-missing":
        x = _flow(m, d["flow"])
        tree = eq.parse(x["equation"])
        if tree[0] != "fn" or tree[1] not in DELAYS:
            raise DefectError(f"flow {d['flow']}: its equation is not a delay")
        x["equation"] = eq.text(tree[2][0])
        fm.drop_unused(m)
        return {**d, "says": f"flow {d['flow']}: its {tree[1]} is missing (it moves at once)", "locus": _ends(m, truth, [d["flow"]]),
                "flows": [d["flow"]]}
    if k == "stock-merged":
        s = d["stock"]
        if s not in m["stocks"]:
            raise DefectError(f"no stock {s}")
        ins = [n for n, f in m["flows"].items() if f["to"] == s]
        outs = [n for n, f in m["flows"].items() if f["from"] == s]
        if len(ins) != 1 or len(outs) != 1:
            raise DefectError(f"stock {s}: merged only when one flow fills it and one drains it")
        locus = _ends(m, truth, [ins[0], outs[0]])
        m["flows"][ins[0]]["to"] = m["flows"][outs[0]]["to"]
        del m["flows"][outs[0]]
        del m["stocks"][s]
        if _uses(m, f"stock.{s}"):
            raise DefectError(f"stock {s} is named by {', '.join(_uses(m, f'stock.{s}'))}")
        _drop_cause(m, f"stock.{s}")
        _drop_cause(m, f"flow.{outs[0]}")
        fm.drop_unused(m)
        return {**d, "says": f"stock {s} is merged away: {ins[0]} goes straight on, {outs[0]} is gone", "locus": locus,
                "flows": [ins[0], outs[0]]}
    if k == "spurious-link":
        x = _flow(m, d["flow"])
        cause = d["cause"]
        share = float(d.get("share") or 0.5)
        size = 1.0
        if record is not None and f"flow.{d['flow']}" in record.clean and cause in record.clean:
            fl, cs = record.clean[f"flow.{d['flow']}"], record.clean[cause]
            mean = lambda xs: sum(abs(v) for v in xs) / max(len(xs), 1)    # noqa: E731
            size = share * mean(fl) / max(mean(cs), 1e-9)
        p = fm.free_name(m, f"{d['flow']}-per-{cause.split('.', 1)[1]}")
        m["parameters"][p] = {"value": float(ye.number(size)), "unit": "1/h", "estimate": True}
        x["equation"] = fm.of_terms([*fm.terms(x["equation"]), (1, eq.parse(f"{p} * {cause}"))])
        x["driven_by"] = [*(x.get("driven_by") or []), f"+{cause}"]
        return {**d, "says": f"flow {d['flow']}: a spurious link from {cause} ({p} = {ye.number(size)})",
                "locus": _ends(m, truth, [d["flow"]]), "flows": [d["flow"]], "parameter": p}
    raise DefectError(f"no defect kind {k}: {', '.join(KINDS)}")


def damaged(truth: dict, defects: list[dict], record=None) -> tuple[dict, list[dict]]:
    m = fm.copy_of(truth)
    planted = [plant(m, truth, d, record) for d in defects]
    return m, planted
