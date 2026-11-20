"""Measures read from the record, for the sensors on the oversight stocks (a stock per measure, named for it):

    ai-spend       dollars spent on AI sessions, all tickets
    repings        re-pings, all tickets
    cycle-hours    the median hours from found to Done, of the last ten tickets done

    measure.py serve      the daemon `measures` (factory/oversight.yaml): one process for the three sensors; the
                          readings asked at the same moment share one read of the record (over ergostat's socket)
    measure.py NAME       one measure, printed once: to compare with the daemon by hand
"""

from __future__ import annotations

import statistics
import sys

from daemon import serve
from tf import items


def measure(what: str, tickets: list[dict]) -> float:
    if what == "ai-spend":
        return round(sum(float(t["fields"].get("ai_cost_usd") or 0) for t in tickets), 6)
    if what == "repings":
        return sum(int(t["fields"].get("repings") or 0) for t in tickets)
    if what == "cycle-hours":
        done = sorted((t for t in tickets if t["fields"].get("cycle_hours") is not None),
                      key=lambda t: t["fields"].get("done_at") or 0)[-10:]
        return round(statistics.median(float(t["fields"]["cycle_hours"]) for t in done), 4) if done else 0
    raise KeyError(f"no measure {what}")


def read(sensors: list[str]) -> dict[str, float]:
    tickets = items("ticket")                              # once, for every reading in the batch
    return {s: measure(s.split(".")[0], tickets) for s in sensors}


def main() -> int:
    what = sys.argv[1]
    if what == "serve":
        return serve(read=read)
    print(measure(what, items("ticket")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
