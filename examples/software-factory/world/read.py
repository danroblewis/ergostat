"""What the product's sensors read from the world: python3 world/read.py users|broken|missing"""

import json
import sys
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "run" / "world" / "state.json"
if not STATE.exists():                       # nobody has used it yet
    print({"users": 20, "broken": 0, "missing": 0}[sys.argv[1]])
    raise SystemExit(0)
s = json.loads(STATE.read_text())
what = sys.argv[1]
print(s["users"] if what == "users" else len(s[what]))
