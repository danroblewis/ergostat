"""Rates as they read naturally (display only). Every rate is kept, fitted and compared per hour
(SPEC §6, §7b); a page shows each in the unit that reads best for its size: per minute above about
60 an hour, per day below about 1 an hour, else per hour. A flow's ``rate-unit:`` (or its stock's,
for the flows it shows) overrides the choice: minute, hour, day or week."""

from __future__ import annotations

UNITS = ("minute", "hour", "day", "week")
PER_HOUR = {"minute": 1 / 60, "hour": 1.0, "day": 24.0, "week": 168.0}   # a rate per hour, times this, is per unit
SUFFIX = {"minute": "/min", "hour": "/h", "day": "/day", "week": "/week"}


def choose(rate: float | None, override: str | None = None) -> str:
    """The unit a rate (per hour) reads best in, or the one the model says."""
    if override in PER_HOUR:
        return override
    if rate is None or rate == 0:
        return "hour"
    r = abs(rate)
    return "minute" if r > 60 else "day" if r < 1 else "hour"


def convert(rate: float | None, unit: str) -> float | None:
    return None if rate is None else rate * PER_HOUR[unit]


def text(rate: float | None, unit: str = "", override: str | None = None) -> str:
    """``12 alerts/min``; ``3 /day`` without a unit; ``?/h`` when it is not known."""
    from .state import fmt
    u = choose(rate, override)
    tail = (unit + SUFFIX[u]) if unit else SUFFIX[u]
    if rate is None:
        return "?" + tail
    return fmt(convert(rate, u)) + (" " if unit else "") + tail


def override_of(spec, flow: str) -> str | None:
    """A flow's ``rate-unit:``, else that of the stock it fills or drains (the first that says one)."""
    if spec is None:
        return None
    f = spec.flows.get(flow)
    if f is None:
        return None
    if f.rate_unit:
        return f.rate_unit
    for end in (f.target, f.source):
        st = spec.stocks.get(end or "")
        if st is not None and st.rate_unit:
            return st.rate_unit
    return None


def overrides(spec) -> dict[str, str]:
    """Every flow's unit the model sets, by flow: what the page needs to show rates as written."""
    return {f: u for f in (spec.flows if spec is not None else {}) if (u := override_of(spec, f))}
