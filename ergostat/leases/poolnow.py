"""A block's pool now (SPEC §9.5): ``pool: N``, or ``pool: {now: stock.S, most: N}``, read from S's level and held to
``[0, most]``. What can't be read as a number (no reading, NaN, infinite, a bool, text) is a pool of 0: the dispatcher
takes nothing new on it. The estimates and the Blocks view, which act on nothing, hold it at 1 and say why
(``said``)."""

from __future__ import annotations

import math


def unread(value) -> bool:
    """Whether a stock's level can't be read as a number: none, a bool, text, NaN or infinite."""
    return isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)


def now(b, value) -> int:
    """The block's pool now, given its stock's level ``value`` (ignored for a pool written as a number)."""
    if b.pool_now is None:
        return b.pool
    if unread(value):
        return 0
    return max(0, min(b.pool, math.floor(value)))


def read_at(p, spec, b, at: float) -> float | None:
    """The stock's level at ``at``: the newest reading, at or before it, of any of its sensors, picked as
    ``Engine.measure`` picks it (a later stamp wins; on equal stamps the sensor first in the model)."""
    st = spec.stocks.get(b.pool_now.name) if b.pool_now else None
    best = None
    for s in (st.sensors.values() if st else ()):
        got = p.measurements.latest(s.series, before=at)
        if got is not None and (best is None or got[0] > best[0]):
            best = got
    return best[1] if best else None


def said(b, value) -> str:
    """Why a pool read from a stock is taken as 1 by what estimates (it is 0 now, or unread); "" when it is not."""
    if b.pool_now is None or now(b, value) > 0:
        return ""
    return f"its pool ({b.pool_now}) {'has no reading' if unread(value) else 'is 0 now'}: estimated at 1 run at once"
