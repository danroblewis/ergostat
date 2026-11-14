"""Five-field cron schedules (minute hour day-of-month month day-of-week), in local time:
``*``, numbers, lists (``1,15``), ranges (``1-5``) and steps (``*/10``, ``8-18/2``). Day-of-week 0
and 7 are Sunday. As in cron, when both day fields are restricted, either one matching is enough."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

FIELDS = (("minute", 0, 59), ("hour", 0, 23), ("day of month", 1, 31), ("month", 1, 12), ("day of week", 0, 7))


class CronError(ValueError):
    pass


def _field(text: str, name: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in text.split(","):
        base, _, step = part.partition("/")
        if base == "*":
            a, b = lo, hi
        elif "-" in base:
            a, b = (int(x) for x in base.split("-", 1))
        else:
            a = b = int(base)
        st = int(step) if step else 1
        if not (lo <= a <= hi and lo <= b <= hi and a <= b and st > 0):
            raise CronError(f"{name}: {part!r} is outside {lo}-{hi}")
        out |= set(range(a, b + 1, st))
    return out


class Cron:
    def __init__(self, expr: str):
        parts = expr.split()
        if len(parts) != 5:
            raise CronError(f"{expr!r}: five fields: minute hour day-of-month month day-of-week")
        try:
            self.sets = [_field(p, n, lo, hi) for p, (n, lo, hi) in zip(parts, FIELDS, strict=True)]
        except ValueError as e:
            raise CronError(f"{expr!r}: {e}") from None
        if 7 in self.sets[4]:
            self.sets[4] = (self.sets[4] - {7}) | {0}
        self.dom_any, self.dow_any = parts[2] == "*", parts[4] == "*"
        self.expr = expr

    def matches(self, t: datetime) -> bool:
        mi, hr, dom, mon, dow = self.sets
        if t.minute not in mi or t.hour not in hr or t.month not in mon:
            return False
        d_ok, w_ok = t.day in dom, (t.isoweekday() % 7) in dow
        if self.dom_any or self.dow_any:
            return d_ok and w_ok
        return d_ok or w_ok

    def next_after(self, ts: float) -> float:
        t = datetime.fromtimestamp(ts).replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(60 * 24 * 366 * 2):
            if self.matches(t):
                return time.mktime(t.timetuple())
            t += timedelta(minutes=1)
        raise CronError(f"{self.expr!r} never matches")
