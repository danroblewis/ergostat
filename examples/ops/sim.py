"""A tiny shared simulation the scripts read and write (.sim.json), with a lock.
One simulated hour (for the backups) passes every two seconds."""
import fcntl
import json
import time
from contextlib import contextmanager
from pathlib import Path

PATH = Path(".sim.json")
HOUR = 2.0                                    # real seconds per simulated hour


@contextmanager
def world():
    with open(".sim.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        start = {"used": 70.0, "waiting": 10, "last_burst": 0.0,
                 "last_backup": now() - 20 * HOUR, "taken": 0, "unsynced": []}
        state = {**start, **(json.loads(PATH.read_text()) if PATH.exists() else {})}
        if not isinstance(state["unsynced"], list):       # a world from before backups were items
            state["unsynced"] = []
        yield state
        PATH.write_text(json.dumps(state))


def say(**line):
    print(json.dumps(line), flush=True)


def now() -> float:
    return time.time()
