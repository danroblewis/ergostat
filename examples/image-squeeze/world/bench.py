"""The benchmark block: measures production on the benchmark (world/benchmark.py) whenever a new
release is in production, and reports each case as an item, met or not, with its best size so far.

Prints, as its block's output: an event per case whose result changed (case.met, case.unmet,
case.measured), and the benchmark score it sets (KB/MP at the quality floor, all thirty cases)."""

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
    sys.stdin.read()
    prod = RUN / "prod"
    if not (prod / "squeeze.py").exists():
        print("production is not there yet", file=sys.stderr)
        return 0
    before = json.loads(OUT.read_text()) if OUT.exists() else {"cases": {}}
    commit = head(prod)
    if before.get("commit") == commit:                      # this release is measured already
        scores(before)
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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(now, indent=1))
    print(f"release {commit[:8]}: {now['met']} of {now['of']} cases met, score {now['score']} KB/MP", file=sys.stderr)
    scores(now)
    return 0


def scores(b: dict) -> None:
    for key, var in (("score", "benchmark-score"), ("photo_score", "photo-score"), ("flat_score", "flat-score")):
        if b.get(key) is not None:
            print(json.dumps({"out": f"variable.{var}", "value": b[key]}))


if __name__ == "__main__":
    sys.exit(main())
