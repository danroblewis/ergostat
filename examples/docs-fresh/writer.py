"""A stand-in for an AI session that rewrites pages. As an ai block with run:, it gets its prompt
and then its context on standard input; the context is the last line. It rewrites the page it is
given first, then the other stale pages, oldest first, and says each (page.rewritten)."""
import json
import sys
import time

from sim import START, world

ctx = json.loads(sys.stdin.read().strip().splitlines()[-1])
cmd = ctx["command"]                                # amount: how many pages (clamped to max); item: which first
time.sleep(1.5)                                     # writing takes a while
with world(START) as w:
    order = sorted(w["stale"], key=lambda p: (p != cmd.get("item"), int(w["stale"][p].split("/")[1])))
    done = order[:int(cmd["amount"])]
    pr = w["next_pr"]
    w["next_pr"] += 1
    for page in done:
        del w["stale"][page]
        if page in w["reported"]:
            w["reported"].remove(page)              # stale again later is new to the scanner
print(json.dumps({"out": "flow.pages-refreshed", "moved": len(done),
                  "note": f"rewrote {', '.join(done) or 'nothing'} in PR #{pr}"}))
for page in done:
    print(json.dumps({"event": "page.rewritten", "item": f"page/{page}", "data": {"pr": f"#{pr}"}}))
