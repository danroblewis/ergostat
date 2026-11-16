"""The benchmark: thirty fixed images (five of each kind), each a case with a target, measured on a
build of squeeze the same way every time: how few kilobytes per megapixel it needs for the image
to look good enough (SSIM at least FLOOR). Like recorded signals a radio must decode: not tests
that pass or fail, but a count of how many the product can do, and how well.

For each case, the quality setting is searched (squeeze is asked for its smallest output that
still looks good enough), so the benchmark measures the code, not the setting the tuner happens
to be at. A case is met when that output is no bigger than its kind's target.

    bin/py world/benchmark.py BUILD_DIR            JSON: every case, and the summary
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import images  # noqa: E402
import judge  # noqa: E402

FLOOR = 0.93
TARGET = {  # kilobytes per megapixel a case of this kind should need, at the floor: squeeze as handed over
    # meets 2 of 30; the plain fixes reach about 9; the rest need better ideas (noisy photos may never)
    "photo": 24.0, "big-photo": 10.0, "gray-photo": 12.0, "screenshot": 8.0, "lineart": 8.0, "logo": 6.0,
}
CASES = [(kind, 1000 + i) for kind in images.KINDS for i in range(5)]
CANNOT = 300.0


def case_id(kind: str, seed: int) -> str:
    return f"case/{kind}-{seed - 999}"


def load(build: Path):
    spec = importlib.util.spec_from_file_location("squeeze_under_test", build / "squeeze.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(build))
    spec.loader.exec_module(mod)
    return mod


def measure(mod, img) -> tuple[float | None, int | None, float | None, str]:
    """The smallest output that looks good enough: (KB/MP, quality, ssim, format), searching the quality."""
    mp = img.size[0] * img.size[1] / 1e6
    best = None
    lo, hi = 5, 95
    tried = {}

    def at(q):
        if q not in tried:
            data, fmt = mod.compress(img.copy(), {"quality": q})
            tried[q] = (len(data), judge.ssim(img, judge.decode(data)), str(fmt))
        return tried[q]

    if at(hi)[1] < FLOOR:                                     # not even at the top: it cannot do this case
        n, s, f = at(hi)
        return None, hi, s, f
    while lo < hi:                                           # the lowest quality that still looks good enough
        mid = (lo + hi) // 2
        if at(mid)[1] >= FLOOR:
            hi = mid
        else:
            lo = mid + 1
    for q, (n, s, f) in tried.items():                        # quality is not always monotone: the smallest that passes
        if s >= FLOOR and (best is None or n < best[0]):
            best = (n, q, s, f)
    n, q, s, f = best
    return round(n / 1024 / mp, 2), q, round(s, 4), f


def run(build: Path) -> dict:
    try:
        mod = load(build)
    except Exception as e:                                    # noqa: BLE001
        return {"error": f"squeeze does not load: {type(e).__name__}: {e}", "cases": {}}
    cases = {}
    for kind, seed in CASES:
        cid = case_id(kind, seed)
        try:
            kb, q, s, f = measure(mod, images.make(kind, seed))
        except Exception as e:                                # noqa: BLE001
            cases[cid] = {"image": kind, "met": False, "error": f"{type(e).__name__}: {e}"[:160], "target": TARGET[kind]}
            continue
        cases[cid] = {"image": kind, "kb_per_mp": kb, "quality": q, "ssim": s, "format": f, "target": TARGET[kind],
                      "met": kb is not None and kb <= TARGET[kind]}
    # a case squeeze cannot make look good enough at any setting counts as CANNOT KB/MP: a penalty
    sizes = [c.get("kb_per_mp") or CANNOT for c in cases.values()]
    score = math.exp(sum(math.log(x) for x in sizes) / len(sizes)) if sizes else None
    return {"cases": cases, "met": sum(1 for c in cases.values() if c["met"]), "of": len(cases),
            "score": round(score, 2) if score else None}                 # geometric mean KB/MP at the floor


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]))))
