"""What the product's sensors read from the service: bin/py world/read.py NAME

    quality bytes-per-mp failures time flat-share          what was served (world/customers.py)
    bytes-saved-low bytes-saved-high quality-change        the running experiment, against production
    candidate-failures candidate-time paired"""

import json
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent / "run"
try:
    s = json.loads((RUN / "world" / "state.json").read_text())
except (OSError, ValueError):
    print("no traffic yet", file=sys.stderr)
    raise SystemExit(1)
c = s.get("candidate") or {}
what = sys.argv[1]
value = {"quality": s["quality"], "bytes-per-mp": s["bytes_per_mp"], "failures": s["failures"], "time": s["time"],
         "flat-share": s["flat_share"],
         "bytes-saved-low": (c.get("bytes_saved") or [0, 0])[0], "bytes-saved-high": (c.get("bytes_saved") or [0, 0])[1],
         "quality-change": c.get("quality_mean", 0.0), "candidate-failures": c.get("failures", 0),
         "candidate-time": c.get("time", 0.0), "paired": c.get("paired", 0)}[what]
print(value)
