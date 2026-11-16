"""A tiny shared simulation the scripts read and write (.sim.json), with a lock.

    python3 sim.py release    upstream releases 0-2 new versions; prints how many, and each as an
                              update to make (update.released, update/http-client-2.4)

It also plays the maintainer, who gets to one PR now and then without telling ergostat:
the review loop's flow is reported by a person (ergostat block review --done N), and here
nobody does, so update-prs-open falls by more than its flows explain. The host still shows the
PR merged, and the PR sensor (updater.py prs) sees it.
"""
import fcntl
import json
import random
import sys
from contextlib import contextmanager
from pathlib import Path

PATH = Path(".sim.json")
START = {"outdated": [], "open": [], "merged_unseen": [], "versions": {}, "next_pr": 101}
PACKAGES = ["http-client", "yaml-reader", "date-utils", "log-format", "test-runner", "image-io", "cli-args",
            "json-schema", "retry", "markdown", "orm", "crypto-box"]


@contextmanager
def world(defaults: dict):
    with open(".sim.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = {**defaults, **(json.loads(PATH.read_text()) if PATH.exists() else {})}
        if not isinstance(state["outdated"], list):         # a world from before updates were items
            state = dict(defaults)
        yield state
        PATH.write_text(json.dumps(state))


def say(**line):
    print(json.dumps(line), flush=True)


if __name__ == "__main__" and sys.argv[1:] == ["release"]:
    released = []
    with world(START) as w:
        for _ in range(random.choice([0, 1, 1, 2])):
            pkg = random.choice(PACKAGES)
            was = w["versions"].get(pkg, random.randint(1, 4))
            w["versions"][pkg] = was + 1
            uid = f"update/{pkg}-{was + 1}.0"
            w["outdated"].append(uid)
            released.append((uid, pkg, was))
        if random.random() < 0.15 and w["open"]:            # the maintainer, between other work
            w["merged_unseen"].append(w["open"].pop(random.randrange(len(w["open"]))))
    say(moved=len(released))
    for uid, pkg, was in released:
        say(event="update.released", item=uid, data={"package": pkg, "from": f"{was}.0", "to": f"{was + 1}.0"})
