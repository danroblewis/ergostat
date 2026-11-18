"""The watcher, a sensor on the arrivals flow: reads Jira for the issues waiting to be picked up (labelled
JIRA_LABEL, in JIRA_PICK_FROM) and records each one it has not seen as a ticket (ticket.found), then prints the
arrivals per hour over the last ten minutes. It reads, and never acts."""

from __future__ import annotations

import sys
import time

import jira
from tf import RUN, items, read_json, say, ticket_id, write_json

WINDOW = 600.0


def main() -> int:
    known = {t["id"] for t in items("ticket")}
    mem = read_json(RUN / "watch.json", {"arrivals": []})
    for issue in jira.waiting():
        tid = ticket_id(issue["key"])
        if tid in known:
            continue
        say({"event": "ticket.found", "item": tid,
             "data": {"key": issue["key"], "title": issue["summary"], "url": issue["url"],
                      "description": issue["description"], "labels": issue["labels"], "found_at": time.time()}})
        mem["arrivals"].append(time.time())
    mem["arrivals"] = [t for t in mem["arrivals"] if t > time.time() - WINDOW]
    write_json(RUN / "watch.json", mem)
    print(round(len(mem["arrivals"]) * 3600 / WINDOW, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
