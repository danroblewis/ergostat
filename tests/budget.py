"""A page's budget, for browser tests: how long after navigation it is usable, and its slowest API call.

    from tests.budget import budget
    b = budget(pg, f"{site}/agents", "() => document.querySelector('#main .ladder-line b')")
    b.check(usable_ms=1000, call_ms=300)        # fails naming the time, or the slow call by its path

``usable`` is a JavaScript function that is true once the reader can use the page (its first answer drawn). The time is
the page's own clock from the navigation's start (``performance.now()``, from the document's time origin) to the first
check that saw it true (checked each animation frame). The calls are the page's call log (``window.ERGOSTAT_CALLS``,
util.js ``timed``: every API call of the old pages and of ``useApi``), each timed to its whole body read, as made up to
then. A page with no call recorded fails: an empty log is never read as fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field

READY = "() => {{ if (!({usable})()) return false; window.__usableAt ??= performance.now(); return true; }}"


@dataclass
class Budget:
    usable_ms: float
    calls: list = field(default_factory=list)       # [{path, url, ms, status}], as the page logged them

    @property
    def slowest(self) -> dict | None:
        return max(self.calls, key=lambda c: c["ms"], default=None)

    def check(self, usable_ms: float = 1000, call_ms: float = 300) -> None:
        assert self.calls, "no API call recorded: the call log (window.ERGOSTAT_CALLS) is empty"
        assert self.usable_ms <= usable_ms, f"usable after {self.usable_ms:.0f} ms (budget {usable_ms:.0f} ms)"
        s = self.slowest
        assert s["ms"] <= call_ms, f"the slowest API call, {s['path']} ({s['url']}), took {s['ms']} ms (budget {call_ms:.0f} ms)"


def budget(pg, url: str, usable: str, timeout_ms: float = 30000) -> Budget:
    """Navigate ``pg`` to ``url`` (a full load), wait until ``usable`` holds, and read the time and the calls."""
    pg.goto(url)
    pg.wait_for_function(READY.format(usable=usable), polling="raf", timeout=timeout_ms)
    usable_ms, calls = pg.evaluate("() => [window.__usableAt, [...(window.ERGOSTAT_CALLS || [])]]")
    return Budget(usable_ms=usable_ms, calls=calls)
