"""A stand-in reviewer: takes the oldest pull request waiting, and approves or rejects it.

    FACTORY_REVIEW=strict  (default) reject when the tests fail, or when the change gets any of
                           the ticket's own examples or reported failures wrong
    FACTORY_REVIEW=lax     approve whatever passes its own tests
    FACTORY_REVIEW=rubber  approve everything
    FACTORY_PACE           seconds it takes (default 3)"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import factory  # noqa: E402

sys.stdin.read()
me = os.environ.get("ERGOSTAT_BLOCK", "reviewer")
r = factory.review()
if r is None:
    print("nothing waits for review", file=sys.stderr)
    factory.moved("merged", 0)
    raise SystemExit(0)
time.sleep(float(os.environ.get("FACTORY_PACE", "3")))
mode = os.environ.get("FACTORY_REVIEW", "strict")
why = ""
if mode != "rubber" and not r["tests_pass"]:
    why = "its tests fail: " + r["tests"].splitlines()[-1]
if mode == "strict" and not why:
    cases = [c for c in (r.get("examples") or []) + (r.get("failures") or []) if "expected" in c]
    probe = ("import json, sys, textkit\ncases = json.load(sys.stdin)\n"
             "print(json.dumps([repr(getattr(textkit, sys.argv[1])(c['input'])) == repr(c['expected']) for c in cases]))")
    p = subprocess.run([sys.executable, "-c", probe, r["op"]], input=json.dumps(cases), cwd=r["workdir"],
                       capture_output=True, text=True, timeout=30)
    results = json.loads(p.stdout) if p.returncode == 0 else [False]
    if not all(results):
        bad = next((c for c, ok in zip(cases, results, strict=False) if not ok), cases[0] if cases else {})
        why = f"{r['op']}({bad.get('input')!r}) should be {bad.get('expected')!r}"
if why:
    factory.reject(r["pr"], why, me)
    print(f"{r['pr']}: rejected: {why}", file=sys.stderr)
    factory.moved("rejected", 1)
else:
    got = factory.approve(r["pr"], "looks right", me)          # merged, or rejected when it no longer merges
    print(f"{r['pr']}: {got}", file=sys.stderr)
    factory.moved(got, 1)
