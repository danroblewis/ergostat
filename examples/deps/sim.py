"""A tiny shared simulation the scripts read and write (.sim.json), with a lock.

    python3 sim.py release    upstream releases 0-2 new versions; prints how many

It also plays the maintainer, who gets to one PR now and then without telling ergostat:
the review loop's flow is reported by a person (ergostat block review --done N), and here
nobody does, so update-prs-open falls by more than its flows explain.
"""
import fcntl
import json
import random
import sys
from contextlib import contextmanager
from pathlib import Path

PATH = Path(".sim.json")
START = {"outdated": 3, "open": 2}


@contextmanager
def world(defaults: dict):
    with open(".sim.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = {**defaults, **(json.loads(PATH.read_text()) if PATH.exists() else {})}
        yield state
        PATH.write_text(json.dumps(state))


if __name__ == "__main__" and sys.argv[1:] == ["release"]:
    with world(START) as w:
        n = random.choice([0, 1, 1, 2])
        w["outdated"] += n
        if random.random() < 0.15 and w["open"] > 0:        # the maintainer, between other work
            w["open"] -= 1
    print(n)
