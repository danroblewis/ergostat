"""A simulated disk (.sim.json): the services' logs fill it at a steady rate, so its usage is
worked out from the time of the last clean. Nothing here runs the services."""
import json
import time
from pathlib import Path

PATH = Path(".sim.json")
WRITES = 0.5            # % per second that the services write


def used() -> float:
    s = json.loads(PATH.read_text()) if PATH.exists() else save(60.0)
    return s["used"] + WRITES * (time.time() - s["t"])


def save(used: float) -> dict:
    s = {"used": used, "t": time.time()}
    PATH.write_text(json.dumps(s))
    return s
