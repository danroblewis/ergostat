"""The dependency updater: two sensors and one worker.

    python3 updater.py audit    how many packages are behind their latest release
    python3 updater.py prs      how many update PRs are open
    python3 updater.py open     open the update PRs it is commanded to (stdin: its context); prints how many
"""
import json
import sys

from sim import START, world

what = sys.argv[1]
with world(START) as w:
    if what == "audit":
        print(w["outdated"])
    elif what == "prs":
        print(w["open"])
    else:
        ctx = json.load(sys.stdin)
        room = 12 - (ctx["inputs"]["stock.update-prs-open"] or 0)    # never more than 12 waiting for review
        n = int(max(0, min(ctx["command"]["amount"], room, w["outdated"])))
        w["outdated"] -= n
        w["open"] += n
        print(n)
