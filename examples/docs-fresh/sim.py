"""A tiny shared simulation the scripts read and write (.sim.json), with a lock.

    python3 sim.py merge      developers merge 0-2 changes, each making a current page stale; prints how many
"""
import fcntl
import json
import random
import sys
from contextlib import contextmanager
from pathlib import Path

PATH = Path(".sim.json")
PAGES = ["install.md", "quickstart.md", "faq.md", "api/auth.md", "api/events.md", "api/items.md", "api/errors.md",
         "guide/loops.md", "guide/goals.md", "guide/blocks.md", "guide/sensors.md", "ops/deploy.md", "ops/backups.md",
         "ops/upgrade.md", "reference/cli.md", "reference/config.md"]


@contextmanager
def world(defaults: dict):
    with open(".sim.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = {**defaults, **(json.loads(PATH.read_text()) if PATH.exists() else {})}
        if not isinstance(state["stale"], dict):            # a world from before pages were items
            state = {**state, **defaults}
        yield state
        PATH.write_text(json.dumps(state))


# each stale page, with the change that made it stale; the pages the scanner has reported stale
START = {"stale": {"install.md": "change/1", "faq.md": "change/2"}, "reported": [], "merged": 2, "next_pr": 201}

if __name__ == "__main__" and sys.argv[1:] == ["merge"]:
    with world(START) as w:
        current = [p for p in PAGES if p not in w["stale"]]
        n = min(random.choice([0, 0, 1, 1, 2]), len(current))
        for page in random.sample(current, n):
            w["merged"] += 1
            w["stale"][page] = f"change/{w['merged']}"
    print(n)
