"""The page picker: how many stale pages to rewrite now, and which first. It commands the writer."""
import json
import sys

from sim import START, world

ctx = json.load(sys.stdin)
goal = ctx["goals"]["docs-current"]
stale, over = goal["value"] or 0, -(goal["error"] or 0)    # error = setpoint - value: negative when over
churn = ctx["inputs"].get("flow.code-changes") or 0
with world(START) as w:
    pages = w["stale"]                                     # what the scanner found: each stale page, by the change that staled it

if over > 0:
    n = over + (1 if churn > 600 else 0)                   # feedforward: code is changing fast, get ahead of it
    page = min(pages, key=lambda p: int(pages[p].split("/")[1]), default="none")   # the page stale longest
    print(json.dumps({"decision": f"{stale:g} stale, {churn:g} changes/h: rewrite {n:g}, {page} first"}))
    print(json.dumps({"out": "block.doc-writer", "command": {"amount": n, "item": page}}))
else:
    print(json.dumps({"decision": "few enough: wait"}))
    print(json.dumps({"out": "block.doc-writer", "command": 0}))
