import json
import sys
import time

from sim import say, world

ctx = json.load(sys.stdin)
page = (ctx.get("trigger") or {}).get("item", "a page")
time.sleep(1.5)                                    # writing takes a while
with world({"stale": 0}) as w:
    done = min(2, w["stale"])
    w["stale"] -= done
say(valve="rewrite-page", amount=done, note=f"rewrote {page} and its neighbours")
say(event="docs.page.rewritten", item=page, data={"pages": done})
