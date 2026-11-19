"""Verification of the modelling subsystem (docs/proposals/self-improvement.md): each example, on a scratch copy, run on
its stand-ins with ``use: modelling`` on (the rule tier, and the AI tier on a cheap model), and what modelling did to it
recorded.

    uv run python scripts/self_improve_runs.py [--seconds 240] [--model haiku] [--no-ai] [--approve] [--out DIR]
        [--parallel 3] [--redesign] [--ports 8792-8799] [example ...]

For each example: ``check --json`` before (findings, craft notes, coherence mismatches); ``ergostat run`` for the
seconds given, with the modelling loop's parameters set for a short run (the rule tier every 20s, the AI tier every
90s, requests read every 30s, the judge's hold-out 90s) and a test policy (``accept: {parameter: auto, description:
auto, unit: auto, equation: auto}``; structure, renames and control wait); with ``--approve``, at 40%, 60% and 80% of
the run, the owner's approval simulated for the changes the rule tier made to the structure, the event names and the
goals, one at a time (each said in the results as the owner's); then ``check --json`` again, and the record read: the requests raised (by
source and code), the changes made by each tier (and by ergostat's own finders), the judge's verdicts, what was
written and by whom, and the AI tier's cost. With ``--redesign`` (docs/proposals/redesign.md) the redesigner runs too
(``redesign: {when: auto}``, every minute) and the owner's promotion of the class is simulated (``accept: {redesign:
auto}``), so a change set judged better is written; its scorecard and cost are recorded. ``thirteen`` is the owner's
13 disconnected stocks (``bench/craft.py``), written fresh. Each run's page is on a port of ``--ports``.
Each run is watched: past ``--threads`` threads or ``--gb`` of memory in
the run's processes it is stopped. Writes ``DIR/results.json`` and prints a table."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERG = [sys.executable, "-m", "ergostat"]
OFFLINE = {"ticket-factory": {"TF_OFFLINE": "1"}}
KEYS = {"rules-every": "20s", "requests-every": "30s", "hold-out": "90s", "judge-every": "20s"}
START = __import__("threading").Lock()
POLICY = "{parameter: auto, description: auto, unit: auto, equation: auto}"


def sh(*args, cwd=None, timeout=600, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([*ERG, *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def configure(path: Path, ai: bool, model: str, redesign: bool = False) -> None:
    """The ``use: modelling`` entry given the short run's parameters (the keys it has already, replaced)."""
    for f in sorted(path.rglob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^(?P<ind> *)use: modelling.*$", text, re.M)
        if not m or "template:" in text[:200]:
            continue
        ind = m.group("ind")
        lines = text.split("\n")
        at = text[:m.start()].count("\n")
        want = {**KEYS, **({"ai": "true", "ai-model": model, "ai-every": "90s"} if ai else {}), "accept": POLICY}
        if ai and not redesign:                           # refinement only: the redesigner (on with ai: true) off
            want["redesign"] = "{when: off}"
        if redesign:
            want.update({"redesign": f"{{when: auto, model: {model}, budget: 0.5, rounds: 3}}", "redesign-every": "60s",
                         "accept": POLICY[:-1] + ", redesign: auto}"})
        end = at + 1
        withs = None
        while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) >= len(ind)):
            if lines[end].strip() == "with:" and len(lines[end]) - len(lines[end].lstrip()) == len(ind):
                withs = end
            end += 1
        if withs is None:
            lines[at + 1:at + 1] = [f"{ind}with:"] + [f"{ind}  {k}: {v}" for k, v in want.items()]
        else:
            i = withs + 1
            sub = None
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > len(ind)):
                d = len(lines[i]) - len(lines[i].lstrip())
                key = lines[i].strip().split(":")[0]
                if sub is None and lines[i].strip():
                    sub = d
                if d == sub and key in want:
                    j = i + 1
                    while j < len(lines) and lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) > d:
                        j += 1
                    del lines[i:j]
                    continue
                i += 1
            lines[withs + 1:withs + 1] = [f"{ind}  {k}: {v}" for k, v in want.items()]
        f.write_text("\n".join(lines), encoding="utf-8")
        return
    raise SystemExit(f"{path}: no use: modelling")


def checked(path: Path) -> dict:
    r = sh("-C", str(path), "check", "--json", timeout=900)
    try:
        got = json.loads(r.stdout)
    except ValueError:
        return {"error": (r.stderr or r.stdout)[-500:]}
    found = got.get("found") or []
    coh = got.get("coherence") or {}
    mism = [f for f in coh.get("findings") or [] if f.get("level") == "mismatch"]
    kinds = {k: f"{x['agree']}/{x['compared']}" for k, x in (coh.get("kinds") or {}).items() if not k.startswith("ergostat.")}
    return {"errors": got.get("errors"), "findings": sum(1 for x in found if x["level"] == "finding"),
            "notes": sum(1 for x in found if x["level"] == "note"),
            "notes_by": dict(Counter(x["code"] for x in found if x["level"] == "note")),
            "findings_by": dict(Counter(x["code"] for x in found if x["level"] == "finding")),
            "mismatches": len(mism), "mismatches_by": dict(Counter(f["code"] for f in mism)), "coherence": kinds}


def processes(path: Path) -> tuple[int, float]:
    """The run's processes' threads and resident memory (GB)."""
    out = subprocess.run(["pgrep", "-f", str(path)], capture_output=True, text=True).stdout.split()
    threads, rss = 0, 0.0
    for pid in out:
        t = subprocess.run(["ps", "-M", "-p", pid], capture_output=True, text=True).stdout.count("\n") - 1
        r = subprocess.run(["ps", "-o", "rss=", "-p", pid], capture_output=True, text=True).stdout.strip()
        threads += max(t, 0)
        rss += float(r or 0) / 1e6
    return threads, rss


def approve(p, notes: list[str]) -> None:
    """The owner's approval, simulated: each change the rule tier made to the structure, the event names or a goal,
    waiting, accepted (the rule tier's changes are the guide's own fixes)."""
    from ergostat.numbers import observe as ob
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import redesign as rd
    if rd.running(p, within=rd.HOLD_FOR):                 # the owner looks in later: a redesign is being made
        notes.append("owner (simulated) waited: a redesign was being made")
        return
    tried: set[str] = set()
    while True:                                           # one at a time: each written changes what the rest stand on
        xs = [x for x in sorted(pr.pending(p), key=lambda x: x.get("created") or 0) if x["id"] not in tried
              and x.get("made_by") == "fixer" and x.get("kind") in ("structure", "rename", "control")]
        if not xs:
            break
        x = xs[0]
        tried.add(x["id"])
        try:
            g = ob.reference(p)
            pr.accept(p, x["id"], {"at": time.time(), "window": g.until - g.since}, by="owner")
            notes.append(f"owner (simulated) accepted {x['kind']}: {x.get('title')}")
            from ergostat import model as mdl
            p.model = mdl.load(p.model.path.parent)
        except Exception as e:
            notes.append(f"owner (simulated) could not accept {x.get('title')}: {e}")


def record(path: Path) -> dict:
    from ergostat import model as mdl
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import requests as rq
    from ergostat.store import Project
    p = Project(mdl.load(path))
    reqs = list(rq.stored(p).values())
    ch = [{**f, "state": st} for _, (st, f) in pr.changes(p).items()]
    tier = {"fixer": "rule", "modeller": "ai", "ergostat": "finders", "improver": "improver", "owner": "owner"}
    made = Counter(tier.get(x.get("made_by"), x.get("made_by")) for x in ch)
    states = Counter(f"{tier.get(x.get('made_by'), x.get('made_by'))}:{x['state']}" for x in ch)
    acc = [x for x in ch if x["state"] in ("accepted", "verified", "regressed")]
    return {"requests": len(reqs), "requests_by_source": dict(Counter(r.get("source") for r in reqs)),
            "requests_by_state": dict(Counter(r["state"] for r in reqs)),
            "requests_by_code": dict(Counter(r.get("code") for r in reqs)),
            "made": dict(made), "states": dict(states),
            "kinds": dict(Counter(f"{tier.get(x.get('made_by'), x.get('made_by'))}:{x.get('kind')}" for x in ch)),
            "accepted": [{"kind": x.get("kind"), "by": tier.get(x.get("made_by"), x.get("made_by")), "title": x.get("title")}
                         for x in acc],
            "verdicts": dict(Counter((x.get("verdict") or {}).get("verdict") for x in ch if x.get("verdict"))),
            "refused": [{"by": x.get("made_by"), "title": x.get("title"), "why": (x.get("why") or "")[:200]}
                        for x in ch if x["state"] == "refused"][:12],
            "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in reqs), 4)}


PORTS: list[int] = []
PORTS_LOCK = __import__("threading").Lock()


def port() -> int:
    with PORTS_LOCK:
        return PORTS.pop(0)


def give_back(n: int) -> None:
    with PORTS_LOCK:
        PORTS.append(n)


def redesigns(path: Path) -> list[dict]:
    """The change sets made in the run: each with its state, verdict, scorecard and cost; and the runs' costs."""
    from ergostat import model as mdl
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import redesign as rd
    from ergostat.store import Project
    p = Project(mdl.load(path))
    out = []
    for pid, (st, f) in pr.changes(p).items():
        if f.get("kind") != "redesign":
            continue
        card = f.get("scorecard") or {}
        out.append({"id": pid, "state": st, "title": f.get("title"), "edits": len((f.get("redesign") or {}).get("edits") or []),
                    "verdict": card.get("verdict"), "why": card.get("why") or f.get("why"),
                    "findings": [card.get("findings", {}).get(k) for k in ("before", "after")],
                    "pieces": [card.get("pieces", {}).get(k) for k in ("before", "after")],
                    "mismatches": [card.get("coherence", {}).get(k) for k in ("mismatches_before", "mismatches_after")],
                    "craft": [card.get("craft", {}).get(k) for k in ("before", "after")],
                    "fit": (card.get("fit") or {}).get("says"), "lost": card.get("lost"),
                    "cost": (f.get("redesign") or {}).get("cost")})
    runs = [e.get("data") or {} for e in p.events.query(n=None, type=rd.RAN)]
    return [{"changes": out, "runs": [{k: r.get(k) for k in ("system", "result", "why", "rounds", "cost", "id")}
                                      for r in runs if r.get("result") != "started"]}]


def one(example: str, a) -> dict:
    src = ROOT / "examples" / example
    work = Path(tempfile.mkdtemp(prefix=f"ergostat-si-{example.replace('/', '-')}-"))
    if example == "thirteen":                             # the owner's 13 disconnected stocks, written fresh
        from ergostat.bench.craft import thirteen
        thirteen(work / example)
        dest = work / example
        f = dest / "ergostat.yaml"
        f.write_text(f.read_text().replace("  modelling: {use: modelling}", "  modelling:\n    use: modelling"))
    elif "/" in example:                                    # a model inside an example: copy the whole example
        top = example.split("/")[0]
        shutil.copytree(ROOT / "examples" / top, work / top, ignore=shutil.ignore_patterns(".ergostat", "__pycache__"))
        dest = work / example
    else:
        dest = work / example
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".ergostat", "__pycache__"))
    configure(dest, not a.no_ai, a.model, a.redesign)
    env = {**os.environ, **OFFLINE.get(example, {})}
    out = {"example": example, "copy": str(dest), "notes": []}
    out["before"] = checked(dest)
    pn = port()
    out["port"] = pn
    with START:                                           # one start at a time
        r = sh("-C", str(dest), "run", "--port", str(pn), env=env)
        time.sleep(3)
    t0 = time.time()
    if r.returncode != 0:
        out["error"] = f"run failed: {r.stderr[-400:]}"
        give_back(pn)
        return out
    peak = (0, 0.0)
    approved = 0.0
    try:
        while time.time() - t0 < a.seconds:
            time.sleep(10)
            th, gb = processes(dest)
            peak = (max(peak[0], th), max(peak[1], gb))
            if th > a.threads or gb > a.gb:
                out["notes"].append(f"stopped by the watchdog: {th} threads, {gb:.1f} GB")
                break
            due = [f for f in (0.4, 0.6, 0.8) if f > approved and time.time() - t0 > a.seconds * f]
            if a.approve and due:                         # the owner looks in now and then
                from ergostat import model as mdl
                from ergostat.store import Project
                approve(Project(mdl.load(dest)), out["notes"])
                approved = max(due)
    finally:
        sh("-C", str(dest), "run", "--stop", env=env)
        give_back(pn)
    out["seconds"] = round(time.time() - t0)
    out["peak"] = {"threads": peak[0], "gb": round(peak[1], 2)}
    out["after"] = checked(dest)
    out["record"] = record(dest)
    if a.redesign:
        out["redesign"] = redesigns(dest)[0]
        out["record"]["cost_usd"] = round(out["record"]["cost_usd"] + sum(float((r.get("cost") or {}).get("usd") or 0)
                                                                          for r in out["redesign"]["runs"]), 4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("examples", nargs="*")
    ap.add_argument("--seconds", type=float, default=240)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--threads", type=int, default=1500)
    ap.add_argument("--gb", type=float, default=6.0)
    ap.add_argument("--out", default="/tmp/ergostat-self-improve")
    ap.add_argument("--redesign", action="store_true", help="the redesigner too, and accept: {redesign: auto}")
    ap.add_argument("--ports", default="8792-8799", help="the ports the runs' pages may use (never the owner's 8790)")
    a = ap.parse_args()
    lo, _, hi = a.ports.partition("-")
    PORTS[:] = [n for n in range(int(lo), int(hi or lo) + 1) if n != 8790]
    a.parallel = min(a.parallel, len(PORTS))
    names = a.examples or sorted(d.name for d in (ROOT / "examples").iterdir() if (d / "ergostat.yaml").is_file())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        for got in ex.map(lambda n: one(n, a), names):
            results.append(got)
            (out / "results.json").write_text(json.dumps(results, indent=1, default=str))
            b, f, rc = got.get("before") or {}, got.get("after") or {}, got.get("record") or {}
            print(f"{got['example']:28s} findings {b.get('findings')}→{f.get('findings')}  notes {b.get('notes')}→{f.get('notes')}  "
                  f"mismatches {b.get('mismatches')}→{f.get('mismatches')}  requests {rc.get('requests')}  made {rc.get('made')}  "
                  f"accepted {len(rc.get('accepted') or [])}  ${rc.get('cost_usd')}  {got.get('error') or ''}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
