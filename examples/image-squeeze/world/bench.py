"""The benchmark's sensor: measures production on the benchmark (world/benchmark.py) whenever a new
release is in production, and reports each case as an item, met or not, with its best size so far.

Prints, as a sensor reading: an observation per case whose result changed (case.met, case.unmet,
case.measured), and the benchmark points.

Points are the percentage fewer kilobytes per megapixel (at the quality floor) squeeze needs than
squeeze as handed over, the first release measured: higher is better, and the seed scores 0. The
KB/MP themselves are kept beside them (score, photo_score, flat_score).

    bench.py                 measure (a new release) and read the points, on all thirty cases
    bench.py --read KEY      only read KEY (photo_points, flat_points, or a KB/MP score) of the last measurement"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "run"
OUT = RUN / "world" / "benchmark.json"


def head(build: Path) -> str:
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=build, capture_output=True, text=True)
    return p.stdout.strip() or "?"


def main() -> int:
    if "--read" in sys.argv:
        key = sys.argv[sys.argv.index("--read") + 1]
        last = json.loads(OUT.read_text()) if OUT.exists() else {}
        if last.get(key) is None:
            print("not measured yet", file=sys.stderr)
            return 1
        print(last[key])
        return 0
    prod = RUN / "prod"
    if not (prod / "squeeze.py").exists():
        print("production is not there yet", file=sys.stderr)
        return 1
    before = json.loads(OUT.read_text()) if OUT.exists() else {"cases": {}}
    commit = head(prod)
    if before.get("commit") == commit:                      # this release is measured already
        print(before.get("benchmark_points", 0.0))
        return 0
    save = RUN / "world" / "cases" / commit[:8]               # what this release made of each case, to look at
    p = subprocess.run([sys.executable, str(ROOT / "world" / "benchmark.py"), str(prod), "--save", str(save)],
                       capture_output=True, text=True, timeout=600)
    now = json.loads(p.stdout)
    for cid, c in now["cases"].items():
        was = before["cases"].get(cid, {})
        best = min([x for x in (c.get("kb_per_mp"), was.get("best")) if x is not None], default=None)
        c["best"] = best
        data = {k: c.get(k) for k in ("image", "original", "output", "kb_per_mp", "target", "quality", "ssim", "format", "best",
                                      "error")}
        data["release"] = commit[:8]
        kind = "case.met" if c["met"] and not was.get("met") else "case.unmet" if was.get("met") and not c["met"] else "case.measured"
        if kind != "case.measured" or c.get("kb_per_mp") != was.get("kb_per_mp") or not was or c.get("output") != was.get("output"):
            print(json.dumps({"event": kind, "item": cid, "data": data}))
    now["commit"] = commit
    seed = before.get("seed") or {k: now[k] for k in ("score", "photo_score", "flat_score")}   # the first release: the seed
    now["seed"] = seed
    for points, score in (("benchmark_points", "score"), ("photo_points", "photo_score"), ("flat_points", "flat_score")):
        now[points] = round(100 * (1 - now[score] / seed[score]), 2) if seed.get(score) else 0.0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")                            # whole, for the other scores' sensors reading it
    tmp.write_text(json.dumps(now, indent=1))
    tmp.replace(OUT)
    print(f"release {commit[:8]}: {now['met']} of {now['of']} cases met, score {now['score']} KB/MP "
          f"({now['benchmark_points']:+g} points)", file=sys.stderr)
    print(now["benchmark_points"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
