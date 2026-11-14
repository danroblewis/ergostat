"""A tiny shared simulation the agents read and write (.sim.json), with a lock."""
import fcntl
import json
import time
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


def say(**line):
    print(json.dumps(line), flush=True)


def now() -> float:
    return time.time()
