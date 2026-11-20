"""The completion estimates held against what happened (SPEC §5a, *Completion estimates*): at past moments, each open
item's finish is estimated from the record before it alone, and compared with when it did finish. Said per set of
components (``eta.ABLATIONS``): the mean absolute error of the p50 (over the items that finished), and the p90's
coverage (the share that finished by their p90; an item unfinished at the record's end counts as a miss once its p90
is before that end, and is left out before)."""

from __future__ import annotations

from ergostat.numbers import eta
from ergostat.numbers.etamodel import read


def backtest(p, spec, kinds: list[str], cuts: list[float], ablations: dict | None = None, runs: int = 100,
             budget: float = 20.0) -> dict[str, dict]:
    """Each set of components → ``{"items", "mae" (seconds), "coverage", "bias" (seconds, p50 − actual)}``."""
    end = p.events.query(n=1)[0]["time"]
    out: dict[str, dict] = {}
    inputs = [read(p, spec, kinds, at, truth=True) for at in cuts]
    for name, flags in (ablations or eta.ABLATIONS).items():
        errs, bias, hit, n = [], [], 0, 0
        for inp in inputs:
            if not inp.items:
                continue
            got = eta.simulate(inp, flags, runs=runs, budget=budget)
            for i, x in got["items"].items():
                done, p50, p90 = inp.finished_at.get(i), x["p50"], x["p90"]
                if done is None:
                    if p90 is not None and p90 < end:
                        n += 1                          # not finished by the record's end, its p90 long past
                    continue
                n += 1
                hit += p90 is None or done <= p90
                if p50 is not None:
                    errs.append(abs(p50 - done))
                    bias.append(p50 - done)
        out[name] = {"items": n, "mae": sum(errs) / len(errs) if errs else None,
                     "coverage": hit / n if n else None, "bias": sum(bias) / len(bias) if bias else None}
    return out
