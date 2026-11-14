import random

from sim import say, world

with world({"outdated": 3, "open": 2}) as w:
    w["outdated"] += random.choice([0, 1, 1, 2])
    say(sensor="dep-audit", value=w["outdated"])
    if w["outdated"] > 5 and w["open"] < 12:            # never more than 12 waiting for review
        n = min(2, w["outdated"] - 5)
        w["outdated"] -= n
        w["open"] += n
        say(controller="deps-current", decision=f"{w['outdated'] + n} outdated: open {n} update PRs")
        say(valve="open-update-pr", amount=n)
    if random.random() < 0.15 and w["open"] > 0:   # the maintainer gets to one, now and then
        w["open"] -= 1
        say(event="pr.merged.noticed", item="update-pr", data={"by": "maintainer"})
    say(sensor="pr-counter", value=w["open"])
