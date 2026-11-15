"""A tiny shared simulation the scripts read and write (.sim.json), with a lock.
One simulated hour passes every two seconds."""
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
        start = {"last_backup": now() - 20 * HOUR, "unsynced": 0}    # the newest backup is 20h old
        state = {**start, **(json.loads(PATH.read_text()) if PATH.exists() else {})}
        yield state
        PATH.write_text(json.dumps(state))


def say(**line):
    print(json.dumps(line), flush=True)


def now() -> float:
    return time.time()
