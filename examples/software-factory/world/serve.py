"""Run a batch of customer requests against one copy of textkit, in a process of its own (the
code is whatever the factory deployed: it may hang or crash). Requests on stdin, answers on
stdout, as JSON."""

import importlib.util
import json
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("textkit", path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    broken = None
except Exception as e:                                  # noqa: BLE001 - the whole product fails to load
    broken = f"{type(e).__name__}: {e}"
out = []
for r in json.load(sys.stdin):
    if broken:
        out.append({"error": f"textkit does not load: {broken}"})
        continue
    fn = getattr(mod, r["op"], None)
    if fn is None or r["op"].startswith("_"):
        out.append({"missing": True})
        continue
    try:
        out.append({"got": fn(r["input"])})
    except Exception as e:                              # noqa: BLE001
        out.append({"error": f"{type(e).__name__}: {e}"})
print(json.dumps(out, default=str))
