import json
import random
import sys

ctx = json.load(sys.stdin)
stale = ctx["state"].get("stale-pages") or 0
pages = ["install.md", "api/auth.md", "api/events.md", "guide/loops.md", "faq.md"]
if stale > 3:
    page = random.choice(pages)
    print(json.dumps({"controller": "docs-current", "decision": f"{stale} stale: rewrite {page}"}))
    print(json.dumps({"event": "docs.rewrite.requested", "item": page, "data": {"stale": stale}}))
else:
    print(json.dumps({"controller": "docs-current", "decision": "few enough: wait"}))
