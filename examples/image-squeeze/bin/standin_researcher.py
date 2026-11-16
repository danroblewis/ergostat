"""A stand-in researcher: while one of the lab's targets is off (small-images, every-case), proposes
the next idea from its notebook (bin/ideas.py) that has not been tried yet. A Claude Code session (FACTORY_AI=claude) reads the results so far and the code,
and proposes its own."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import lab  # noqa: E402
from ideas import IDEAS  # noqa: E402

ctx = {}
for line in reversed(sys.stdin.read().splitlines()):     # the prompt, then the block's input as one JSON line
    try:
        ctx = json.loads(line)
        break
    except ValueError:
        continue
me = os.environ.get("ERGOSTAT_BLOCK", "researcher")
goals = ctx.get("goals") or {}
targets = [goals.get(g) for g in ("small-images", "every-case") if goals.get(g)]
if targets and all(g.get("status") == "holding" for g in targets):   # the lab's targets are met: nothing to look for
    print("both targets hold: nothing to propose", file=sys.stderr)
    print(json.dumps({"out": "flow.proposed", "moved": 0}))
    raise SystemExit(0)
tried = {h["fields"].get("key") for h in lab.items("hypothesis")}
idea = next((i for i in IDEAS if i["key"] not in tried), None)
if idea is None:
    print("the notebook is empty: every idea has been tried", file=sys.stderr)
    print(json.dumps({"out": "flow.proposed", "moved": 0}))
    raise SystemExit(0)
hid = lab.propose(idea["title"], idea["idea"], idea["key"], me)
print(f"{hid}: {idea['title']}", file=sys.stderr)
print(json.dumps({"out": "flow.proposed", "moved": 1}))
