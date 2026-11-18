"""The watcher: reads what the factory's tracker says has happened (the world's feed) and records it as events
about items, the way a sensor reads a tracker's stream of changes. It is the sensor on the owner's directions,
and its number is how many direction items arrived per hour over the last ten minutes."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from world import sim  # noqa: E402

MEM = ROOT / "run" / "watch.json"
WINDOW = 600.0


def main() -> int:
    mem = json.loads(MEM.read_text()) if MEM.exists() else {"offset": 0, "arrivals": []}
    with sim.advanced():
        pass
    lines, mem["offset"] = sim.feed(mem["offset"])
    now = time.time()
    for e in lines:
        print(json.dumps({"event": e["type"], "item": e["item"], "data": e["data"]}), flush=True)
        if e["type"] == "work.directed":
            mem["arrivals"].append(now)
    mem["arrivals"] = [t for t in mem["arrivals"] if t > now - WINDOW]
    MEM.write_text(json.dumps(mem))
    print(round(len(mem["arrivals"]) * 3600 / WINDOW, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
