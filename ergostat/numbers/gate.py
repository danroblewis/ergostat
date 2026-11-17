"""The gate a change to the model passes before anyone tests it (SPEC §12e): it must not worsen the fit of the whole
model, nor of what it touches and the parts next to them, beyond a tolerance, whatever it does to the part it was
fitted on. A value fitted on one stock alone ("each part alone") can make that stock fit at once and the whole replay
far worse (its stock read through flows the part-alone fit took as measured): both are said, and the change is
refused before the judge spends record on it.

What a change touches (``touched``): the parts it names or moves, a parameter through the flows and auxiliaries
whose equations use it, and a flow through the stocks it fills and drains. Its **neighbourhood** is those and every
part one link from them (a cause, an effect, a flow's stocks, a goal or a block that reads or acts on them). The
**local** fit is the scaled error over the stocks of the neighbourhood (each stock's mean squared error over its mean
square, as the total is made); the **whole** fit is the total."""

from __future__ import annotations

from ..spec.ir import Spec

WORSE = 0.10                # the scaled error may rise by this share at most, whole or local
TRIFLE = 1e-4               # ... and a rise smaller than this is no rise


def _ref(r) -> str:
    return f"{r.kind}.{r.name}"


def users_of(spec: Spec, parameter: str) -> list[str]:
    """The parts whose equations name a parameter."""
    return [f"{k}.{x.name}" for k, t in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)) for x in t.values()
            if x.equation and parameter in x.equation.parameters]


def links(spec: Spec) -> dict[str, set[str]]:
    """Every link in the model, both ways: a flow to its stocks, a part to its causes and what its equation names
    (parameters too), a goal to what it holds, a block to what it reads and acts on."""
    adj: dict[str, set[str]] = {}

    def link(a: str, b: str) -> None:
        if a != b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for n, x in table.items():
            r = f"{kind}.{n}"
            adj.setdefault(r, set())
            for s in (getattr(x, "source", None), getattr(x, "target", None)):
                if s:
                    link(r, f"stock.{s}")
            for c in x.driven_by:
                link(r, _ref(c))
            if x.equation:
                for c in x.equation.refs:
                    link(r, c)
                for q in x.equation.parameters:
                    link(r, f"parameter.{q}")
    for n in spec.stocks:
        adj.setdefault(f"stock.{n}", set())
    for n, g in spec.goals.items():
        link(f"goal.{n}", _ref(g.of))
    for n, b in spec.blocks.items():
        for r in (*b.reads(), *b.targets()):
            link(f"block.{n}", _ref(r))
    return adj


def touched(spec: Spec, refs) -> set[str]:
    """What a change touches: the parts it names, a parameter's users, a flow's stocks."""
    out: set[str] = set()
    for r in refs or []:
        r = str(r)
        kind, _, name = r.partition(".")
        if kind == "parameter":
            out |= set(users_of(spec, name))
        elif kind == "goal" and name in spec.goals:
            out |= {r, _ref(spec.goals[name].of)}
        else:
            out.add(r)
    for r in list(out):
        kind, _, name = r.partition(".")
        f = spec.flows.get(name) if kind == "flow" else None
        if f is not None:
            out |= {f"stock.{s}" for s in (f.source, f.target) if s}
    return out


def neighbourhood(spec: Spec, refs, k: int = 1) -> set[str]:
    """What a change touches and every part ``k`` links from it."""
    adj = links(spec)
    seen = touched(spec, refs)
    edge = set(seen)
    for _ in range(k):
        edge = {n for r in edge for n in adj.get(r, ())} - seen
        seen |= edge
    return seen


def stocks_of(spec: Spec, refs, k: int = 1) -> list[str]:
    """The stocks of the neighbourhood: what the local fit is scored on."""
    return sorted(r for r in neighbourhood(spec, refs, k) if r.startswith("stock.") and r[6:] in spec.stocks)


def scaled(fit: dict | None, ref: str) -> float | None:
    """One stock's scaled error in a fit (its mean squared error over its mean square), when the fit judged it."""
    s = ((fit or {}).get("stocks") or {}).get(ref)
    if not s or s.get("too_little") or s.get("nmse") is None:
        return None
    return float(s["nmse"])


def total(fit: dict | None) -> float | None:
    return ((fit or {}).get("total") or {}).get("nmse")


def like_for_like(fit_b: dict | None, fit_a: dict | None) -> dict:
    """The whole model's scaled error before and after, over the stocks both fits judge (a change that makes a stock
    worked out by an equation brings it into the total, and a total over other stocks is not the same number); the
    totals as they are when the fits say nothing per stock."""
    refs = sorted(set((fit_b or {}).get("stocks") or {}) | set((fit_a or {}).get("stocks") or {}))
    both = [(scaled(fit_b, r), scaled(fit_a, r)) for r in refs]
    both = [(b, a) for b, a in both if b is not None and a is not None]
    if not both:
        return {"before": total(fit_b), "after": total(fit_a), "stocks": None}
    return {"before": sum(b for b, _ in both) / len(both), "after": sum(a for _, a in both) / len(both), "stocks": len(both)}


def local(fit_b: dict | None, fit_a: dict | None, stocks: list[str]) -> dict | None:
    """The scaled error over the stocks both fits judged, before and after, and the stock that moved most."""
    both = [(r, scaled(fit_b, r), scaled(fit_a, r)) for r in stocks]
    both = [(r, b, a) for r, b, a in both if b is not None and a is not None]
    if not both:
        return None
    worst = max(both, key=lambda t: t[2] - t[1])
    return {"parts": [r for r, _, _ in both], "before": sum(b for _, b, _ in both) / len(both),
            "after": sum(a for _, _, a in both) / len(both), "worst": {"ref": worst[0], "before": worst[1], "after": worst[2]}}


def _worse(b: float | None, a: float | None, tolerance: float = WORSE) -> bool:
    return b is not None and a is not None and a > b * (1 + tolerance) and a - b > TRIFLE


def said(b: float | None, a: float | None) -> str:
    """Two scaled errors and which way they went, in words: "0.788 → 18.5, 23× worse"."""
    if b is None or a is None:
        return f"{_sig(b)} → {_sig(a)}"
    if abs(a - b) <= TRIFLE or (b and abs(a - b) <= 1e-3 * b):
        return f"{_sig(b)} → {_sig(a)}, the same"
    if a > b:
        how = f"{a / b:.3g}× worse" if b > 0 and a >= 2 * b else f"{(a - b) / b:.0%} worse" if b > 0 else "worse"
    else:
        how = f"{(b - a) / b:.0%} better" if b > 0 else "better"
    return f"{_sig(b)} → {_sig(a)}, {how}"


def _sig(x) -> str:
    return "–" if x is None else f"{x:.3g}"


def check(spec: Spec, fit_b: dict | None, fit_a: dict | None, refs, tolerance: float = WORSE) -> dict:
    """The whole model's fit and the local fit, before and after, and why the change is refused (``worse``), or None:
    refused when either rises by more than ``tolerance`` (and not by a trifle)."""
    stocks = stocks_of(spec, refs)
    whole = like_for_like(fit_b, fit_a)
    near = local(fit_b, fit_a, stocks)
    out = {"whole": whole, "local": near, "neighbourhood": stocks, "worse": None}
    bad_whole = _worse(whole["before"], whole["after"], tolerance)
    bad_near = bool(near) and _worse(near["before"], near["after"], tolerance)
    if bad_whole or bad_near:                       # both numbers, whichever is worse, so neither hides the other
        why = [f"the whole model's scaled error {said(whole['before'], whole['after'])}"]
        if near:
            w = near["worst"]
            why.append(f"near what it touches ({', '.join(near['parts'])}) {said(near['before'], near['after'])}"
                       + (f", {w['ref']} most ({said(w['before'], w['after'])})" if len(near["parts"]) > 1 else ""))
        out["worse"] = "; ".join(why if bad_whole else why[::-1])
    return out


def summary(g: dict) -> str:
    """Both numbers, whatever they did: the whole model's and near what the change touches."""
    w, n = g["whole"], g.get("local")
    out = f"whole model {said(w['before'], w['after'])}"
    if n:
        out += f"; near what it touches ({', '.join(n['parts'])}) {said(n['before'], n['after'])}"
    return out
