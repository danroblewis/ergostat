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
        # as in Vixie cron, a day field starting with * (even */2) counts as unrestricted
        self.dom_any, self.dow_any = parts[2].startswith("*"), parts[4].startswith("*")
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
        """The next matching minute after ``ts``, within eight years (29 February comes every four);
        whole days that cannot match are skipped."""
        t = datetime.fromtimestamp(ts).replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = t + timedelta(days=366 * 8)
        mi, hr, dom, mon, dow = self.sets
        while t < end:
            day_ok = t.month in mon and (
                (t.day in dom and (t.isoweekday() % 7) in dow) if (self.dom_any or self.dow_any)
                else (t.day in dom or (t.isoweekday() % 7) in dow))
            if not day_ok:
                t = (t + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if self.matches(t):
                return time.mktime(t.timetuple())
            t += timedelta(minutes=1)
        raise CronError(f"{self.expr!r} never matches")
