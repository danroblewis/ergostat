"""The tickets, for the owner:

    tickets.py list              every ticket: its state, and why it stopped when it did
    tickets.py retry KEY         send a stopped ticket back to the step that stopped it
"""

from __future__ import annotations

import sys

from tf import items, record


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "list"
    tickets = items("ticket")
    if what == "list":
        for t in sorted(tickets, key=lambda t: t.get("first") or 0):
            f = t["fields"]
            print(f"{t['id']:22} {t['state']:14} {f.get('title', '')[:50]}")
            if t["state"] == "stopped":
                print(f"{'':22} stopped at {f.get('stopped_at')}: {f.get('stopped_why')}")
        return 0
    if what == "retry":
        tid = sys.argv[2] if sys.argv[2].startswith("ticket/") else f"ticket/{sys.argv[2]}"
        t = next((t for t in tickets if t["id"] == tid), None)
        if not t or t["state"] != "stopped":
            sys.exit(f"{tid} is not stopped")
        back = t["fields"].get("stopped_from")
        record("ergostat.item.reopened", tid, {"reopened": {"to": back, "from": "stopped"}}, by="owner")
        print(f"{tid} back to {back}")
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
