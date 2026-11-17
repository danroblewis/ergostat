"""A stand-in improver: free, seconds, no judgement of its own. ergostat's own finders' changes (the calibration
of the parameters marked to estimate, the structural changes from check's findings, the simplify rules) are items the
judge tests as they are; while the model's fit is off its goal, the stand-in adds what they declined: an estimate the
calibration kept and did not propose (within two standard errors of the value written, say), since the judge decides
on the record that comes after it, not the stand-in. Each is a propose line with its evidence: the fit statistic that
says what is wrong, and the rule it follows. At most two a run, and never a second change to a part one waits on.

Its run is a session item (session/improver-...) like the AI's, at no cost, so each run's cost is on the Items page
either way."""

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOST = 2                                   # proposals a run


def ergostat(*args) -> dict | list:
    cmd = os.environ.get("ERGOSTAT_CMD")
    base = shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]
    out = subprocess.run([*base, *args], capture_output=True, text=True, timeout=600).stdout
    try:
        return json.loads(out)
    except ValueError:
        return {}


def declined(fit: dict) -> list[dict]:
    """The estimates of the last calibration (each part alone) that ergostat kept and did not propose, with a value:
    the newest estimates file in the state directory (ERGOSTAT_STATE_DIR)."""
    d = Path(os.environ.get("ERGOSTAT_STATE_DIR") or "") / "estimates"
    files = sorted((f for f in d.glob("*.json") if f.stem.count(".") == 0), key=lambda f: f.stat().st_mtime) if d.is_dir() else []
    try:
        got = json.loads(files[-1].read_text()) if files else {}
    except (OSError, ValueError):
        return []
    out = []
    for e in got.values():
        if e.get("value") is None or not e.get("refused") or e.get("at_bound") or e.get("at_range"):
            continue
        name = e.get("parameter")
        edit = ergostat("improve", "--edit-value", f"{name}={e['value'] * 3600:.4g}s" if e.get("duration") else
                        f"{name}={e['value']:.4g}")
        if not edit.get("files"):
            continue
        before = fit.get("stocks") or {}
        rs = [{"says": f"as written, the replay of {r.split('.', 1)[1]} {before[r]['says']}",
               "evidence": f"fit:{r}.{worst_stat(before[r])}"}
              for r in e.get("fitted_to") or [] if (before.get(r) or {}).get("says")]
        rs.append({"says": f"the record's estimate of {name} is not the value written; ergostat did not propose it "
                           f"({e['refused']}), so let the record after it judge", "evidence": "rule:parameter-assessment"})
        out.append({"kind": "parameter", "parts": [f"parameter.{name}", *(e.get("fitted_to") or [])],
                    "title": f"{name}: the record's estimate, for the judge", "edit": {"files": edit["files"]},
                    "reasons": rs, "confidence": 0.3, "parameters": {name: e["value"]}, "target": f"parameter.{name}"})
    return out



def event(type: str, item: str, data: dict) -> None:
    print(json.dumps({"event": type, "item": item, "data": data}), flush=True)


def worst_stat(s: dict) -> str:
    """The statistic that says what is wrong with a replay: its bias, its unequal variation, or its R²."""
    if (s.get("um") or 0) >= max(s.get("us") or 0, 0.1):
        return "um"
    if (s.get("us") or 0) >= 0.1:
        return "us"
    return "r2" if s.get("r2") is not None else "mape"


def clashes(x: dict, mine: list[dict]) -> bool:
    """A candidate already under test changes the same parameter or part: one at a time."""
    ps = set(x.get("parameters") or {})
    return any(ps & set(y.get("parameters") or {}) or (x.get("target") and x.get("target") == y.get("target")) for y in mine)


def main() -> int:
    sys.stdin.read()                                    # the prompt and the block's input: the stand-in needs neither
    me = os.environ.get("ERGOSTAT_BLOCK", "improver")
    run = (os.environ.get("ERGOSTAT_RUN") or f"{time.time_ns():x}")[:8]
    item = f"session/{me}-{run}"
    started = time.time()
    event("session.started", item, {"role": me, "model": "stand-in", "started": started})
    ergostat("proposals", "--json")                     # calibrate (each part alone) and look for structure again
    fit = ergostat("fit", "--json") or {}
    waiting = fit.get("proposals") or []
    mine = list(waiting)                                # every change waiting, whoever made it: one at a time for a part
    said = 0
    seen = ROOT / "run" / "improver-tried.json"         # what it proposed before: proposed once, judged once
    try:
        tried = set(json.loads(seen.read_text()))
    except (OSError, ValueError):
        tried = set()
    for x in declined(fit):                             # what ergostat declined, for the judge to decide
        key = x["target"]                               # each parameter once: the judge's verdict stands
        if said >= MOST or clashes(x, mine) or key in tried:
            continue
        tried.add(key)
        print(json.dumps({"propose": {k: x[k] for k in ("kind", "parts", "title", "edit", "reasons", "confidence")}}),
              flush=True)
        mine.append(x)
        said += 1
    (ROOT / "run").mkdir(exist_ok=True)
    seen.write_text(json.dumps(sorted(tried)))
    rec = {"cost_usd": 0.0, "turns": 0, "seconds": round(time.time() - started, 1), "error": False,
           "said": f"proposed {said} change{'s' if said != 1 else ''} ergostat declined" if said else
                   "nothing new to propose: nothing declined, or a change to it is waiting already"}
    (ROOT / "run").mkdir(exist_ok=True)
    with open(ROOT / "run" / "costs.jsonl", "a") as f:
        f.write(json.dumps({"at": time.time(), "role": me, "item": item, **rec}) + "\n")
    event("session.ran", item, rec)
    print(rec["said"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
