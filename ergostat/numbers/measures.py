"""The model's own quality, ergostat's built-in measures (SPEC §12e), each a reference ``ergostat.model.NAME``
read by a sensor (``sensor: {builtin: ergostat.model.fit}``) on a stock or an auxiliary, by ergostat itself
(``ergostat measure ergostat.model.fit``, in a process of its own, so a slow fit never holds up the engine). Each
is a measurement of the model against the record, like any sensor's, so a goal can hold it and a block act on it:

- **ergostat.model.fit**: the scaled error of the replay on the reference window, the Fit page's total (Oliva 2003: each
  stock's mean squared error over its own mean square, averaged); none while there is too little record;
- **ergostat.model.unexplained**: the share of each stock's change over the last hour that its flows do not explain (the
  residuals, SPEC §12b), |unexplained| / (|explained| + |unexplained|), averaged over the stocks that moved;
- **ergostat.model.unidentified-loops**: the goals whose loop closes and whose process (u to y) the model does not hold,
  declared or identified (SPEC §8, §12d);
- **ergostat.model.open-findings**: what ``ergostat check`` finds, errors aside (structure, signs, extreme conditions, control).
"""

from __future__ import annotations

import time

from ..spec.ir import MODEL_MEASURES


class MeasureError(Exception):
    pass


def fit(p) -> float | None:
    from . import fit as ft
    _, run, got = ft.compute(p, {"at": time.time()})
    t = got.get("total")
    return t.get("nmse") if t and run.valid else None


def unexplained(p) -> float | None:
    from .. import state
    res = state.snapshot(p, state.WINDOW, None).get("residuals") or {}
    shares = []
    for r in res.values():
        u, e = abs(r.get("unexplained") or 0.0), abs(r.get("explained") or 0.0)
        if u + e > 1e-12:
            shares.append(u / (u + e))
    return sum(shares) / len(shares) if shares else 0.0


def loops_unidentified(p) -> float:
    spec = p.model.spec
    n = 0
    for g in spec.goals.values():
        try:
            closes = spec.loop(g.name).closes
        except Exception:
            closes = False
        if closes and not g.process:
            n += 1
    return float(n)


def findings(p) -> float:
    from ..spec import read
    _, problems = read(p.model.path)
    return float(sum(1 for x in problems if x.level != "error"))


def _meta():
    from . import meta
    return meta.READERS


READERS = {"ergostat.model.fit": fit, "ergostat.model.unexplained": unexplained,
           "ergostat.model.unidentified-loops": loops_unidentified, "ergostat.model.open-findings": findings,
           **{n: (lambda p, n=n: _meta()[n](p)) for n in ("ergostat.model.accepted-per-day", "ergostat.model.regressed",
                                                          "ergostat.model.verified-share", "ergostat.model.fit-gained",
                                                          "ergostat.model.cost-per-accepted")}}


def measure(p, name: str) -> float | None:
    if not name.startswith("ergostat."):           # by hand, the short name will do: fit, open-findings
        name = "ergostat.model." + name.removeprefix("model.")
    if name not in MODEL_MEASURES:
        raise MeasureError(f"no measure {name!r}: {', '.join(MODEL_MEASURES)}")
    if getattr(p.model, "spec", None) is None:
        raise MeasureError("the model is an ergostat.toml: its measures are read from ergostat.yaml")
    return READERS[name](p)


def all_of(p) -> dict[str, float | None]:
    out = {}
    for n in MODEL_MEASURES:
        try:
            out[n] = measure(p, n)
        except Exception as e:                        # one measure that cannot be read leaves the others
            out[n] = None
            out[f"{n}_error"] = f"{type(e).__name__}: {e}"
    return out
