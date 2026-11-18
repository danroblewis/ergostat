"""Measures read from the record, for the sensors on the oversight stocks:

    measure.py ai-spend       dollars spent on AI sessions, all tickets
    measure.py repings        re-pings, all tickets
    measure.py cycle-hours    the median hours from found to Done, of the last ten tickets done
"""

from __future__ import annotations

import statistics
import sys

from tf import items


def main() -> int:
    what = sys.argv[1]
    tickets = items("ticket")
    if what == "ai-spend":
        print(round(sum(float(t["fields"].get("ai_cost_usd") or 0) for t in tickets), 6))
    elif what == "repings":
        print(sum(int(t["fields"].get("repings") or 0) for t in tickets))
    elif what == "cycle-hours":
        done = sorted((t for t in tickets if t["fields"].get("cycle_hours") is not None),
                      key=lambda t: t["fields"].get("done_at") or 0)[-10:]
        print(round(statistics.median(float(t["fields"]["cycle_hours"]) for t in done), 4) if done else 0)
    else:
        sys.exit(f"no measure {what}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
