"""Durations as people write them: ``30s``, ``5m``, ``2h``, ``1d``, or a number of seconds."""

from __future__ import annotations

import re

UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


class DurationError(ValueError):
    pass


def parse_duration(value, where: str = "duration") -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value <= 0:
            raise DurationError(f"{where}: must be more than 0")
        return float(value)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w)?\s*", str(value))
    if not m or float(m.group(1)) <= 0:
        raise DurationError(f"{where}: {value!r} is not a duration (like 30s, 5m, 2h, 1d)")
    return float(m.group(1)) * UNITS[m.group(2) or "s"]


def human(seconds: float) -> str:
    """``95`` -> ``1m35s``; short and exact enough for a table."""
    s = abs(seconds)
    if s < 1:
        return f"{s * 1000:.0f}ms"
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        m, r = divmod(int(s), 60)
        return f"{m}m{r:02d}s" if r and m < 10 else f"{m}m"
    if s < 86400:
        h, r = divmod(int(s), 3600)
        return f"{h}h{r // 60:02d}m" if r // 60 and h < 10 else f"{h}h"
    d, r = divmod(int(s), 86400)
    return f"{d}d{r // 3600}h" if r // 3600 and d < 10 else f"{d}d"
