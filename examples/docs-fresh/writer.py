"""A stand-in for an AI session that rewrites pages. As an ai block with run:, it gets its prompt
and then its context on standard input; the context is the last line."""
import json
import sys
import time

from sim import START, world

ctx = json.loads(sys.stdin.read().strip().splitlines()[-1])
cmd = ctx["command"]                                # amount: how many pages (clamped to max); item: which first
time.sleep(1.5)                                     # writing takes a while
with world(START) as w:
    done = min(int(cmd["amount"]), w["stale"])
    w["stale"] -= done
print(json.dumps({"out": "flow.pages-refreshed", "moved": done, "note": f"rewrote {cmd.get('item', 'a page')} and its neighbours"}))
print(json.dumps({"event": "docs.page.rewritten", "item": f"doc/{cmd.get('item')}", "data": {"pages": done}}))
