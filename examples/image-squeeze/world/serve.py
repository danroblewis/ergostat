"""One build of squeeze, run on one batch of images, in a process of its own (the code is whatever
the factory built: it may crash, hang or cheat on the clock). Reads the batch on stdin, writes one
result per image on stdout:

    {"bytes": 23110, "format": "jpeg", "ms": 4.1, "ssim": 0.957}   or   {"error": "..."}

usage: serve.py BUILD_DIR"""

import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import images  # noqa: E402
import judge  # noqa: E402

build = Path(sys.argv[1])
req = json.load(sys.stdin)
out = []
try:
    spec = importlib.util.spec_from_file_location("squeeze", build / "squeeze.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(build))
    spec.loader.exec_module(mod)
    broken = None
except Exception as e:                                       # noqa: BLE001 - the build does not even load
    broken = f"squeeze does not load: {type(e).__name__}: {e}"
for kind, seed in req["images"]:
    if broken:
        out.append({"error": broken})
        continue
    img = images.make(kind, seed)
    try:
        t0 = time.perf_counter()
        data, fmt = mod.compress(img.copy(), dict(req["settings"]))
        ms = (time.perf_counter() - t0) * 1000
        got = judge.decode(data)
        out.append({"bytes": len(data), "format": str(fmt), "ms": round(ms, 2), "ssim": round(judge.ssim(img, got), 5)})
    except Exception as e:                                   # noqa: BLE001
        out.append({"error": f"{type(e).__name__}: {e}"[:200]})
print(json.dumps(out))
