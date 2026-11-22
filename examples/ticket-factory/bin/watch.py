"""The watcher, the sensor on the arrivals flow: reads Jira for the issues waiting to be picked up (labelled
JIRA_LABEL, in JIRA_PICK_FROM) and records each one it has not seen as a ticket (ticket.found), then reads the
arrivals per hour over the last ten minutes. It reads, and never acts.

It also records Jira's links on the tickets (ticket.linked: blocked_by, duplicates, relates_to, parent, each a whole
set; jira.links() for the mapping). No lock is taken: each reading compares Jira's answer with the fold as read at
that reading. If two readings overlap (the daemon and a manual run whose output is recorded), the older answer may
land last, and the record matches Jira's latest answer again after the next reading, not at once. Tickets only, the
first LINKS_MOST (500) labelled issues only, only the links the Jira account can see, and an issue with a link or
parent that can't be read keeps the relations it has (said in the log).

    watch.py serve     its daemon (factory/intake.yaml): asked for each reading, it looks at Jira and answers
    watch.py           once, printing the events and the reading as a run: sensor would (by hand, or to compare)
"""

from __future__ import annotations

import sys
import time

import jira
from daemon import serve
from tf import RUN, items, log, read_json, record, say, ticket_id, write_json

WINDOW = 600.0


def look(found) -> float:
    """Each new issue given to found(event), then each ticket's changed links, then the arrivals per hour."""
    known = {t["id"]: t.get("fields") or {} for t in items("ticket")}
    mem = read_json(RUN / "watch.json", {"arrivals": []})
    for issue in jira.waiting():
        tid = ticket_id(issue["key"])
        if tid in known:
            continue
        found({"event": "ticket.found", "item": tid,
               "data": {"key": issue["key"], "title": issue["summary"], "url": issue["url"],
                        "description": issue["description"], "labels": issue["labels"], "found_at": time.time()}})
        known[tid] = {}                                    # just found: no links yet
        mem["arrivals"].append(time.time())
    mem["arrivals"] = [t for t in mem["arrivals"] if t > time.time() - WINDOW]
    write_json(RUN / "watch.json", mem)
    linked(known, found)
    return round(len(mem["arrivals"]) * 3600 / WINDOW, 2)


def linked(known: dict[str, dict], found) -> None:
    """Jira's links, for the tickets in the record (as read at this reading's start) or just found: each relation that
    differs from the ticket's fold, as a whole set. Compared with the fold, never with what was last written, so a
    reading whose older answer landed last is put right at the next reading."""
    try:
        answer = jira.linked()
    except jira.JiraError as e:
        return log(f"Jira's links not read, nothing written: {e}")
    for key, rels in sorted(answer.items()):
        tid = ticket_id(key)
        if tid not in known:                               # tickets only: ticket.linked never makes an item
            continue
        if rels is None:
            log(f"{key}: a link or parent that can't be read; its relations kept as they are")
            continue
        differ = {r: {"set": ids} for r, ids in rels.items() if sorted(known[tid].get(r) or []) != ids}
        if differ:
            found({"event": "ticket.linked", "item": tid, "data": differ})


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
