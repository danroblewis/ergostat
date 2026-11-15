"""A tiny shared simulation the scripts read and write (.sim.json), with a lock.

    python3 sim.py merge      developers merge 0-2 changes, each making a page stale; prints how many
"""
import fcntl
import json
import random
import sys
from contextlib import contextmanager
from pathlib import Path

PATH = Path(".sim.json")


@contextmanager
def world(defaults: dict):
    with open(".sim.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = {**defaults, **(json.loads(PATH.read_text()) if PATH.exists() else {})}
        yield state
        PATH.write_text(json.dumps(state))


START = {"stale": 2, "merged": 0}

if __name__ == "__main__" and sys.argv[1:] == ["merge"]:
    with world(START) as w:
        n = random.choice([0, 0, 1, 1, 2])
        w["stale"] += n
        w["merged"] += n
    print(n)
