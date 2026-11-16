"""A stand-in developer: takes the next hypothesis and writes the code its notebook has for it
(bin/ideas.py), as a change to squeeze in its own branch, then submits it. An idea the notebook
has no code for (one a Claude researcher proposed) it cannot build, and abandons. A Claude Code
session (FACTORY_AI=claude) writes its own code from the idea.

    FACTORY_PACE  seconds it takes (default 2)"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import lab  # noqa: E402
from ideas import IDEAS  # noqa: E402

sys.stdin.read()
me = os.environ.get("ERGOSTAT_BLOCK", "developer")
h = lab.claim(me)
if h is None:
    print("nothing to start", file=sys.stderr)
    print(json.dumps({"out": "flow.started", "moved": 0}))
    raise SystemExit(0)
if not h.get("resumed"):
    print(json.dumps({"out": "flow.started", "moved": 1}))
time.sleep(float(os.environ.get("FACTORY_PACE", "2")))
code = next((i["code"] for i in IDEAS if i["key"] == h.get("key")), None)
if code is None:
    lab.abandon(h["hypothesis"], "the stand-in developer has no code for this idea", me)
    print(json.dumps({"out": "flow.abandoned", "moved": 1}))
    raise SystemExit(0)
src = Path(h["workdir"]) / "squeeze.py"
if code.strip() not in src.read_text():                  # resumed: it may be written already
    src.write_text(src.read_text().rstrip() + "\n\n" + code.strip() + "\n")
got = lab.submit(h["hypothesis"], h["title"], me)
print(f"{h['hypothesis']}: {got}", file=sys.stderr)
print(json.dumps({"out": "flow.abandoned" if got.startswith("abandoned") else "flow.submitted", "moved": 1}))
