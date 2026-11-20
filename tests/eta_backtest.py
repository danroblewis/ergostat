"""The completion estimates held against what happened (SPEC §5a, *Completion estimates*): at past moments, each open
item's finish is estimated from the record before it alone, and compared with when it did finish. Said per set of
components (``eta.ABLATIONS``): the mean absolute error of the p50 (over the items that finished), its bias (the
estimate's mean against what happened: a median is below the mean of a skewed finish, so its own bias is not one), the
share finished by their p50 (a half, unbiased), and the p90's
coverage (the share that finished by their p90; one estimated beyond the horizon that finished is a miss). An item
unfinished at the record's end is a miss when its p90 is before that end, and otherwise cannot be judged: it is
counted apart (``unresolved``), so a record must run long enough past its cuts for that to be few."""

from __future__ import annotations

from ergostat.numbers import eta
from ergostat.numbers.etamodel import read


def backtest(p, spec, kinds: list[str], cuts: list[float], ablations: dict | None = None, runs: int = 100,
             budget: float = 20.0) -> dict[str, dict]:
    """Each set of components → ``{"items", "unresolved", "mae" (seconds, of the p50), "coverage" (by the p90),
    "p50" (the share finished by their p50: a half when unbiased), "bias" (seconds, the mean − actual)}``."""
    end = p.events.query(n=1)[0]["time"]
    out: dict[str, dict] = {}
    inputs = [read(p, spec, kinds, at, truth=True) for at in cuts]
    for name, flags in (ablations or eta.ABLATIONS).items():
        errs, bias, hit, half, n, open_, none = [], [], 0, 0, 0, 0, 0
        for inp in inputs:
            if not inp.items:
                continue
            got = eta.simulate(inp, flags, runs=runs, budget=budget)
            if not got["runs"]:                          # no run finished within the budget: not worked out
                none += len(inp.items)
                continue
            for i, x in got["items"].items():
                done, p50, p90 = inp.finished_at.get(i), x["p50"], x["p90"]
                if done is None:
                    if p90 is not None and p90 < end:
                        n += 1                          # not finished by the record's end, its p90 long past
                    else:
                        open_ += 1
                    continue
                n += 1
                hit += p90 is not None and done <= p90
                half += p50 is not None and done <= p50
                if p50 is not None:
                    errs.append(abs(p50 - done))
                if x.get("mean") is not None:
                    bias.append(x["mean"] - done)
        out[name] = {"items": n, "unresolved": open_, "not_worked_out": none, "mae": sum(errs) / len(errs) if errs else None,
                     "coverage": hit / n if n else None, "p50": half / n if n else None, "bias": sum(bias) / len(bias) if bias else None}
    return out
