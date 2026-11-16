"""The dependency updater: a sensor and a worker.

    python3 updater.py prs      how many update PRs are open; and each one the host shows merged
                                since it last looked (update.merged), whoever merged it
    python3 updater.py open     open the update PRs it is commanded to (stdin: its context), oldest
                                update first; says each one (update.pr-opened) and how many
"""
import json
import sys

from sim import START, say, world

what = sys.argv[1]
if what == "prs":
    with world(START) as w:
        merged, w["merged_unseen"] = w["merged_unseen"], []
        n = len(w["open"])
    for uid in merged:
        say(event="update.merged", item=uid, data={"merged_by": "maintainer"})
    print(n)
else:
    ctx = json.load(sys.stdin)
    with world(START) as w:
        room = 12 - (ctx["inputs"]["stock.update-prs-open"] or 0)    # never more than 12 waiting for review
        n = int(max(0, min(ctx["command"]["amount"], room, len(w["outdated"]))))
        opened = [(w["outdated"].pop(0), w["next_pr"] + i) for i in range(n)]
        w["next_pr"] += n
        w["open"] += [uid for uid, _ in opened]
    say(moved=n)
    for uid, pr in opened:
        say(event="update.pr-opened", item=uid, data={"pr": f"#{pr}"})
