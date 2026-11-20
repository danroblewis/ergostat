"""How long things last, from a record that has not finished them all (Kaplan and Meier, 1958): the product-limit
estimate of the survival function with **censoring** (a stay still going is known to have lasted at least its age,
and is counted at risk until then, never as ended), and an item's **residual life** given its age, S(a + t) / S(a).

Past the longest stay observed the curve goes on as an exponential **tail** whose mean is the mean residual of the
longest tenth of the stays (each one's excess over the 90th percentile; at least a second): an item older than every
stay seen is given that tail, never nothing left. The stays are taken as they were seen, from when each began: a
stay that began before the record does (left-truncated) counts from its first move. Times in seconds."""

from __future__ import annotations

import bisect
import math


class KM:
    """``ended``: the lengths of stays that ended; ``going``: the ages of those still going (censored)."""

    def __init__(self, ended: list[float], going: list[float] = ()):
        ev = sorted(max(0.0, x) for x in ended)
        ce = sorted(max(0.0, x) for x in going)
        self.n, self.events = len(ev) + len(ce), len(ev)
        self.times, self.surv = [], []                       # S just after each time an end was seen
        s, i, j, at_risk = 1.0, 0, 0, self.n
        while i < len(ev):
            t = ev[i]
            while j < len(ce) and ce[j] < t:                 # censored before t: no longer at risk
                at_risk -= 1
                j += 1
            d = 0
            while i < len(ev) and ev[i] == t:
                d, i = d + 1, i + 1
            s *= 1.0 - d / max(at_risk, 1)
            self.times.append(t)
            self.surv.append(s)
            at_risk -= d
        self.neg = [-x for x in self.surv]                   # (non-decreasing: searched by bisection)
        every = sorted(ev + ce)
        self.last = every[-1] if every else 0.0
        top = every[int(0.9 * len(every)):]
        self.tail = sum(x - top[0] for x in top) / len(top) if top else 60.0
        if self.tail < 1.0:                                  # (the longest all alike: every stay's mean instead)
            self.tail = max(1.0, sum(every) / len(every))

    def S(self, t: float) -> float:
        """The chance a stay lasts longer than ``t``."""
        k = bisect.bisect_right(self.times, t)
        s = self.surv[k - 1] if k else 1.0
        return s * math.exp(-(t - self.last) / self.tail) if t > self.last else s

    def quantile(self, u: float, age: float = 0.0) -> float:
        """The residual life, from ``age``, at which the chance of still going falls to ``u`` (0 < u < 1): the time
        ``t`` with S(age + t) <= u · S(age)."""
        if age >= self.last or self.S(age) <= 0:          # older than every stay seen: the tail
            return self.tail * math.log(1.0 / u)
        target = u * self.S(age)
        k = bisect.bisect_right(self.times, age)
        j = bisect.bisect_left(self.neg, -target, lo=k)     # the first end past ``age`` with S <= target
        if j < len(self.times):
            return self.times[j] - age
        s_end = self.S(self.last)
        if s_end <= 0:
            return self.last - age
        return self.last - age + self.tail * math.log(s_end / target)

    def sample(self, rnd, age: float = 0.0) -> float:
        """A residual life given ``age``, drawn by inverting S(age + t) / S(age)."""
        return self.quantile(min(max(rnd.random(), 1e-9), 1 - 1e-9), age)

    def mean_residual(self, age: float = 0.0, steps: int = 100) -> float:
        """E[T − a | T > a], by the quantiles (a midpoint sum over ``steps``)."""
        return sum(self.quantile((i + 0.5) / steps, age) for i in range(steps)) / steps
