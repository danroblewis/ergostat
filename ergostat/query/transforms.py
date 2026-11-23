"""What is done to a series of buckets once aggregated: a rate, a change, a running total, a moving average."""

from __future__ import annotations

from .parse import RATE_PER

SHORT = {"second": "s", "minute": "min", "hour": "h", "day": "d"}


def per_for(rates: list[float | None]) -> str:
    """The unit of time that shows per-second ``rates`` readably: the shortest in which the largest is at least 1."""
    top = max((abs(x) for x in rates if x is not None), default=0.0)
    return next((w for w, s in RATE_PER.items() if top * s >= 1), "day")


def plain_rate(values: list, spans: list[float]) -> list:
    """Per second: each bucket's amount over the seconds it covers (a part bucket at the window's end is not a dip)."""
    return [None if v is None or s <= 0 else v / s for v, s in zip(values, spans, strict=True)]


def counter_rate(values: list, spans: list[float], before: float | None) -> list:
    """Per second, of a counter's last reading in each bucket: its increase since the reading before (``before``: the
    last one ahead of the window), a fall being a reset, counted from zero. Over a gap, the increase is spread over
    the whole time since that reading; a bucket with no reading has no rate."""
    out: list = []
    prev, elapsed = before, 0.0
    for v, s in zip(values, spans, strict=True):
        elapsed += s
        if v is None:
            out.append(None)
            continue
        out.append(None if prev is None or elapsed <= 0 else (v - prev if v >= prev else v) / elapsed)
        prev, elapsed = v, 0.0
    return out


def delta(values: list) -> list:
    """The change from the last bucket with a value."""
    out: list = []
    prev = None
    for v in values:
        out.append(None if v is None or prev is None else v - prev)
        prev = v if v is not None else prev
    return out


def cumulative(values: list) -> list:
    """The running total; a bucket with no value holds it; nothing before the first value."""
    out: list = []
    total = None
    for v in values:
        if v is not None:
            total = (total or 0.0) + v
        out.append(total)
    return out


def moving_avg(values: list, window: int) -> list:
    """The mean of the last ``window`` buckets' values; None where they hold none."""
    out: list = []
    for i in range(len(values)):
        got = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        out.append(sum(got) / len(got) if got else None)
    return out
