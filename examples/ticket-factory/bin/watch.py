"""The watcher, the sensor on the arrivals flow: reads Jira for the issues waiting to be picked up (labelled
JIRA_LABEL, in JIRA_PICK_FROM) and records each one it has not seen as a ticket (ticket.found), then reads the
arrivals per hour over the last ten minutes. It reads, and never acts.

    watch.py serve     its daemon (factory/intake.yaml): asked for each reading, it looks at Jira and answers
    watch.py           once, printing the events and the reading as a run: sensor would (by hand, or to compare)
"""

from __future__ import annotations

import sys
import time

import jira
from daemon import serve
from tf import RUN, items, read_json, record, say, ticket_id, write_json

WINDOW = 600.0


def look(found) -> float:
    """Each new issue given to found(event), then the arrivals per hour."""
    known = {t["id"] for t in items("ticket")}
    mem = read_json(RUN / "watch.json", {"arrivals": []})
    for issue in jira.waiting():
        tid = ticket_id(issue["key"])
        if tid in known:
            continue
        found({"event": "ticket.found", "item": tid,
               "data": {"key": issue["key"], "title": issue["summary"], "url": issue["url"],
                        "description": issue["description"], "labels": issue["labels"], "found_at": time.time()}})
        mem["arrivals"].append(time.time())
    mem["arrivals"] = [t for t in mem["arrivals"] if t > time.time() - WINDOW]
    write_json(RUN / "watch.json", mem)
    return round(len(mem["arrivals"]) * 3600 / WINDOW, 2)


def read(sensors: list[str]) -> dict[str, float]:
    # A daemon's reading carries only its number, so each new ticket is recorded over ergostat's socket, as the
    # sensor's own (its source is the sensor's name, arrivals.main, as when its command printed it), before the reading.
    def found(e):
        record(e["event"], e["item"], e["data"], by=sensors[0])
    return {s: look(found) for s in sensors[:1]}


def main() -> int:
    if sys.argv[1:] == ["serve"]:
        return serve(read=read)
    print(look(say))
    return 0


if __name__ == "__main__":
    sys.exit(main())
