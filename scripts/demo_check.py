"""Run a fresh copy of each demo repository for a while, then check it the way a user would: the model is whole,
the agents ran, every API answers, and the page draws with no errors (screenshots with
Playwright when it is installed).

    python scripts/demo_check.py [--seconds 12] [--shots DIR] [demo ...]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "examples"   # each example, run from a fresh copy
ERGOSTAT = [sys.executable, "-m", "ergostat"]
# What a demo that can reach real services is run with here: offline, against its fakes, never the services
OFFLINE = {"ticket-factory": {"TF_OFFLINE": "1"}}


def sh(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([*ERGOSTAT, *args], cwd=cwd, capture_output=True, text=True, timeout=60)


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def page_errors(url: str, shot: Path | None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (playwright is not installed: the page itself is not checked)", flush=True)
        return []
    errs: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        for route in ("diagram", "diagram?view=blocks", "diagram?view=process", "loops", "agents", "items",
                      "record", "residuals", "check", "guide"):
            pg.goto(f"{url}/{route}")
            pg.wait_for_timeout(1800)
            if shot and route in ("diagram", "diagram?view=blocks", "diagram?view=process", "agents"):
                pg.screenshot(path=str(shot.with_name(f"{shot.stem}-{route.replace('?view=', '-')}.png")))
            if route == "diagram" and pg.locator(".node").count() == 0:
                errs.append("the diagram drew no parts")
        b.close()
    return errs


def snapshot_errors(demo: Path) -> list[str]:
    """The snapshot, opened with every request refused: it must draw and ask for nothing."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    out = demo.parent / "snapshot.html"
    r = sh("-C", str(demo), "snapshot", "-o", str(out))
    if r.returncode != 0:
        return [f"snapshot failed: {r.stderr}"]
    errs: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: errs.append(f"snapshot: {e}"))
        pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith("file:")
                 else (errs.append(f"snapshot asked for {rt.request.url}"), rt.abort()))
        for route in ("diagram", "diagram?view=blocks", "diagram?view=process", "loops", "agents", "items", "record", "residuals", "guide"):
            pg.goto(f"file://{out}#/{route}")
            pg.wait_for_timeout(1200)
            if route == "diagram" and pg.locator(".node").count() == 0:
                errs.append("the snapshot's diagram drew no parts")
        b.close()
    return errs


def items_as_before(url: str, spec) -> list[str]:
    """Each item of a kind with no fold rules, whose events carry plain data, folds as it did before
    changesets (SPEC §5a): each key's latest value."""
    from urllib.parse import quote
    out = []
    kinds = getattr(spec, "items", None) or {}
    for it in get(f"{url}/api/items")["items"][:60]:
        k = kinds.get(it["kind"] or "")
        if k is not None and k.fold:
            continue
        evs = get(f"{url}/api/events?item={quote(it['id'], safe='')}&n=5000&runs=1")
        if any(e.get("patch") is not None or e.get("set") is not None for e in evs):
            continue
        d = get(f"{url}/api/items/{quote(it['id'], safe='')}")
        if d.get("refused"):                                  # refused on purpose (a late run's line, fenced)
            continue
        was: dict = {}
        for e in evs:
            if not e["type"].startswith("ergostat.lease."):    # a lease is ergostat's own field (SPEC §9.5)
                was.update(e.get("data") or {})
        now = {k: v for k, v in d["fields"].items() if not (k == "lease" and isinstance(v, dict))}   # an item's own lease
        if now != was:
            out.append(f"item {it['id']}: folds to {json.dumps(now)[:200]}, not {json.dumps(was)[:200]} as before")
    return out


def incoherent(demo: Path, notes: list[str]) -> list[str]:
    """The coherence check (coherence.py) on what the run recorded: a coherent demo's three views agree wherever there
    is record enough to compare; each kind's score is a note."""
    from ergostat import coherence as co
    from ergostat import model as mdl
    from ergostat.store import Project
    p = Project(mdl.load(demo))
    spec = getattr(p.model, "spec", None)
    if spec is None:
        return []
    got = co.of_project(p, spec)
    notes.extend(f"note: coherence: {co.score_line(k, x)}" for k, x in got["kinds"].items() if x["compared"])
    return [f"coherence: {f['code']} ({f['pair']}): {f['message'][:300]}" for f in got["findings"] if f["level"] == "mismatch"]


def fresh_copy(demo: Path) -> Path:
    """The demo's tracked files in a new folder, so a check never shares files (a simulation, a
    working repository) with a copy of the demo that is already running."""
    dest = Path(tempfile.mkdtemp(prefix=f"ergostat-check-{demo.name}-")) / demo.name
    files = subprocess.run(["git", "-C", str(demo), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo / f, dest / f)
    return dest


def fmt(x) -> str:
    return f"{x:.3g}" if isinstance(x, float) else str(x)


notes: list[str] = []


def pair(demo: Path) -> tuple[Path, Path | None, list[str]]:
    """A demo of two ergostats (``pair.json``: a remote system and the local model that reads it, SPEC §4c): the remote
    started on its port with a token made for the local one, which is then checked as the demo. (the local demo, the
    remote to stop after, its port flag)."""
    spec = json.loads((demo / "pair.json").read_text())
    remote, local = demo / spec["remote"], demo / spec["local"]
    r = sh("-C", str(remote), "run", "--port", str(spec["remote_port"]))
    if r.returncode != 0:
        raise RuntimeError(f"the remote did not start: {r.stderr}")
    tok = sh("-C", str(remote), "remote", "token", spec["local"])
    (local / spec["token_file"]).write_text(tok.stdout.strip())
    url = json.loads(sh("-C", str(remote), "--json").stdout)["web"]
    y = local / "ergostat.yaml"                                      # wherever the remote's page came up
    y.write_text(y.read_text().replace(f"http://127.0.0.1:{spec['remote_port']}", url))
    return local, remote, ["--port", str(spec["local_port"])]


def check(demo: Path, seconds: float, shots: Path | None) -> list[str]:
    os.environ.update(OFFLINE.get(demo.name, {}))
    demo = fresh_copy(demo)
    problems = []
    notes.clear()
    remote, port = None, []
    if (demo / "pair.json").exists():
        try:
            demo, remote, port = pair(demo)
        except RuntimeError as e:
            return [str(e)]
    c = sh("-C", str(demo), "check")
    if c.returncode != 0:
        if remote:
            sh("-C", str(remote), "run", "--stop")
        return [f"check failed: {c.stdout}{c.stderr}"]
    r = sh("-C", str(demo), "run", *port)
    if r.returncode != 0:
        if remote:
            sh("-C", str(remote), "run", "--stop")
        return [f"run failed: {r.stderr}"]
    try:
        time.sleep(seconds)
        st = json.loads(sh("-C", str(demo), "--json").stdout)
        if not st["running"] or not st["web"]:
            problems.append("not running, or no web page")
        agents = json.loads(sh("-C", str(demo), "agent", "--json").stdout)
        from ergostat import model as mdl
        spec = getattr(mdl.load(demo), "spec", None)
        paced = {n for n in (spec.blocks if spec else {}) if spec.commanders_of(n)}   # every: paces it; a command runs it
        for name, a in agents.items():
            if a["runs_itself"] and a["every"] and a["runs"] == 0 and name not in paced:
                problems.append(f"agent {name} never ran")
            if a["failing"]:
                problems.append(f"agent {name} is failing")
            if a["refused"]:
                problems.append(f"agent {name} had lines refused")
        sensed_by = {n: a for n, a in agents.items() for r in a["roles"] if r["kind"] == "sensor" for n in [r["name"]]}
        readme = (demo / "README.md").read_text() if (demo / "README.md").exists() else ""
        for name, lp in st["loops"].items():
            if lp["status"] == "open" and name in readme:      # missing on purpose: the example points it out
                continue
            people_only = all(not (sensed_by.get(s) or {}).get("runs_itself") for s in lp["sensors"])
            if lp["status"] == "open" or (lp["status"] == "unknown" and not people_only):
                problems.append(f"loop {name} is {lp['status']}")
        res = json.loads(sh("-C", str(demo), "residual", "--json").stdout)
        notes.extend(f"note: stock {k}: {fmt(v['unexplained'])} unexplained" + (f" ({v['why']})" if v.get("why") else "")
                     for k, v in res.items() if v.get("significant"))
        url = st["web"]
        for path in ("status", "graph", "graph?view=process", "loops", "agents", "events", "items", "residuals", "parts"):
            get(f"{url}/api/{path}")
        problems += items_as_before(url, spec)
        problems += incoherent(demo, notes)
        if spec is not None:                                     # each loop as a control engineer reads it
            from urllib.parse import quote
            for g in spec.goals:
                get(f"{url}/api/loop-control?goal={quote(g)}")
        problems += page_errors(url, shots / demo.name if shots else None)
        problems += snapshot_errors(demo)
    finally:
        sh("-C", str(demo), "run", "--stop")
        if remote:
            sh("-C", str(remote), "run", "--stop")
    problems += rollup_errors(demo)
    return problems


def rollup_errors(demo: Path) -> list[str]:
    """The demo's own record, every item rolled up whole (rollup.py), folds to the same items, with and
    without their transcripts' lines; and the archive holds every event that went."""
    from ergostat import model as mdl
    from ergostat.rollup import archived, compact
    from ergostat.spec import items as its
    from ergostat.store import Project
    p = Project(mdl.load(demo))
    spec = getattr(p.model, "spec", None)
    if spec is None or not spec.items:
        return []

    def folded(tr: bool) -> dict:
        by: dict = {}
        for e in p.events.of_items(None, skip=() if tr else (its.TRANSCRIPT_TYPES,)):
            by.setdefault(e["item"], []).append(e)
        return {i: its.fold(i, evs, its.kind_of(spec, i), transcript=tr).as_dict(moves=True) for i, evs in by.items()}
    before = {tr: folded(tr) for tr in (False, True)}
    got = compact(p, now=time.time() + 10 * 365 * 86400)
    out = [f"rolled up, item {i} folds differently ({'with' if tr else 'without'} its transcript)"
           for tr in (False, True) for i, it in folded(tr).items() if before[tr].get(i) != it]
    for tr in (False, True):                       # the item index (spec/itemindex.py) is the fold of the record
        idx = {i.id: i.as_dict(moves=True) for i in its.project(p.events, spec, transcript=tr)}
        out += [f"the item index differs from the record for {i} ({'with' if tr else 'without'} its transcript)"
                for i in set(idx) | set(before[tr]) if idx.get(i) != before[tr].get(i)][:5]
    out += [f"rolled up, item {i}: {a['total']} events in its full history, not {before[True][i]['events']}"
            for i in before[True] if (a := archived(p, i, n=0)) and a["total"] != before[True][i]["events"]]
    notes.append(f"note: rolled up {got['events']} events of {got['items']} items; every item folds as before")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("demos", nargs="*")
    ap.add_argument("--seconds", type=float, default=12)
    ap.add_argument("--shots", type=Path)
    a = ap.parse_args()
    os.environ.setdefault("ERGOSTAT_HOME", tempfile.mkdtemp(prefix="ergostat-demos-"))
    names = a.demos or sorted(p.name for p in DEMOS.iterdir() if (p / "ergostat.yaml").exists() or (p / "ergostat.toml").exists()
                              or (p / "pair.json").exists())
    if a.shots:
        a.shots.mkdir(parents=True, exist_ok=True)
    bad = 0
    for n in names:
        probs = check(DEMOS / n, a.seconds, a.shots)
        print(f"{'ok  ' if not probs else 'FAIL'} {n}" + "".join(f"\n       {p}" for p in probs + notes), flush=True)
        bad += bool(probs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
