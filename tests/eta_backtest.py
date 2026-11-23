"""The completion estimates held against what happened, per set of components (SPEC §5a, *Completion estimates*): the
core is ``ergostat/numbers/etacheck.py``, the eta worker's own (read at a cut with truth, simulate, score)."""

from __future__ import annotations

from ergostat.numbers import eta
from ergostat.numbers.etacheck import score
from ergostat.numbers.etamodel import read


def backtest(p, spec, kinds: list[str], cuts: list[float], ablations: dict | None = None, runs: int = 100,
             budget: float = 20.0) -> dict[str, dict]:
    """Each set of components → ``etacheck.score`` at ``cuts``, against the record's end."""
    end = p.events.query(n=1)[0]["time"]
    inputs = [read(p, spec, kinds, at, truth=True) for at in cuts]
    return {name: score(inputs, end, flags, runs=runs, budget=budget) for name, flags in (ablations or eta.ABLATIONS).items()}
