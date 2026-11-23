"""The arithmetic of a non-time X: pairing two series bucket by bucket, histogram bins, and the capping of points.
Pure: what is read from the record is in ``points.py``, and how a request is answered in ``engine.py``."""

from __future__ import annotations

import math

from .parse import X_TYPES

X_OF = {"items": list(X_TYPES), "moves": ["time", "query", "category", "bins"], "counts": ["time", "query", "category", "bins"],
        "series": ["time", "query", "bins"], "events": ["time", "query", "category", "bins"], "frequency": ["frequency"]}


def finite(v) -> bool:
    return v is not None and math.isfinite(v)


def paired(xs: list, ys: list) -> tuple[list, list]:
    """One point per bucket; a bucket missing either coordinate holds no point (both null), which breaks a trajectory."""
    out_x, out_y = [], []
    for x, y in zip(xs, ys, strict=True):
        ok = finite(x) and finite(y)
        out_x.append(x if ok else None)
        out_y.append(y if ok else None)
    return out_x, out_y


def edges(values: list[float], bins: int) -> list[float]:
    """``bins`` equal bins from the least value to the greatest; all alike, one unit wide around it."""
    lo, hi = min(values), max(values)
    if lo == hi:
        lo, hi = lo - 0.5, hi + 0.5
    out = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
    out[-1] = hi
    return out


def bin_of(v: float, e: list[float]) -> int:
    """Which bin holds ``v``: a value on an edge belongs to the bin above it, and the greatest to the last bin. The first
    guess is corrected against the edges, since (v - lo) / width can round across one (0.3 / 0.1 is 2.999...)."""
    n = len(e) - 1
    i = min(n - 1, max(0, int((v - e[0]) / (e[-1] - e[0]) * n)))
    if v < e[i] and i > 0:
        i -= 1
    elif i < n - 1 and v >= e[i + 1]:
        i += 1
    return i


def centres(e: list[float]) -> list[float]:
    return [(a + b) / 2 for a, b in zip(e, e[1:], strict=False)]
