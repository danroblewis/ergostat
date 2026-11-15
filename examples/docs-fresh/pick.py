"""The page picker: how many stale pages to rewrite now, and which first. It commands the writer."""
import json
import random
import sys

ctx = json.load(sys.stdin)
goal = ctx["goals"]["docs-current"]
stale, over = goal["value"] or 0, -(goal["error"] or 0)    # error = setpoint - value: negative when over
churn = ctx["inputs"].get("flow.code-changes") or 0
pages = ["install.md", "api/auth.md", "api/events.md", "guide/loops.md", "faq.md"]

if over > 0:
    n = over + (1 if churn > 600 else 0)                   # feedforward: code is changing fast, get ahead of it
    page = random.choice(pages)
    print(json.dumps({"decision": f"{stale:g} stale, {churn:g} changes/h: rewrite {n:g}, {page} first"}))
    print(json.dumps({"out": "block.doc-writer", "command": {"amount": n, "item": page}}))
else:
    print(json.dumps({"decision": "few enough: wait"}))
    print(json.dumps({"out": "block.doc-writer", "command": 0}))
