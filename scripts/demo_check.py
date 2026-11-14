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

DEMOS = Path.home() / "ergostat-demos"
ERGOSTAT = [sys.executable, "-m", "ergostat"]


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
        for route in ("diagram", "diagram?view=blocks", "diagram?view=wiring", "loops", "agents", "parts", "parts?kind=valve",
                      "record", "residuals", "check", "guide"):
            pg.goto(f"{url}/#/{route}")
            pg.wait_for_timeout(1800)
            if shot and route in ("diagram", "diagram?view=blocks", "diagram?view=wiring", "agents"):
                pg.screenshot(path=str(shot.with_name(f"{shot.stem}-{route.replace('?view=', '-')}.png")))
            if route == "diagram" and pg.locator(".node").count() == 0:
                errs.append("the diagram drew no parts")
        b.close()
    return errs


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


def check(demo: Path, seconds: float, shots: Path | None) -> list[str]:
    demo = fresh_copy(demo)
    problems = []
    notes.clear()
    c = sh("-C", str(demo), "check")
    if c.returncode != 0:
        return [f"check failed: {c.stdout}{c.stderr}"]
    r = sh("-C", str(demo), "run")
    if r.returncode != 0:
        return [f"run failed: {r.stderr}"]
    try:
        time.sleep(seconds)
        st = json.loads(sh("-C", str(demo), "--json").stdout)
        if not st["running"] or not st["web"]:
            problems.append("not running, or no web page")
        agents = json.loads(sh("-C", str(demo), "agent", "--json").stdout)
        for name, a in agents.items():
            if a["runs_itself"] and a["every"] and a["runs"] == 0:
                problems.append(f"agent {name} never ran")
            if a["failing"]:
                problems.append(f"agent {name} is failing")
            if a["refused"]:
                problems.append(f"agent {name} had lines refused")
        sensed_by = {n: a for n, a in agents.items() for r in a["roles"] if r["kind"] == "sensor" for n in [r["name"]]}
        for name, lp in st["loops"].items():
            people_only = all(not (sensed_by.get(s) or {}).get("runs_itself") for s in lp["sensors"])
            if lp["status"] == "open" or (lp["status"] == "unknown" and not people_only):
                problems.append(f"loop {name} is {lp['status']}")
        res = json.loads(sh("-C", str(demo), "residual", "--json").stdout)
        notes.extend(f"note: stock {k}: {fmt(v['unexplained'])} unexplained" + (f" ({v['why']})" if v.get("why") else "")
                     for k, v in res.items() if v.get("significant"))
        url = st["web"]
        for path in ("status", "graph", "graph?view=wiring", "loops", "agents", "events", "items", "residuals", "parts"):
            get(f"{url}/api/{path}")
        problems += page_errors(url, shots / demo.name if shots else None)
    finally:
        sh("-C", str(demo), "run", "--stop")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("demos", nargs="*")
    ap.add_argument("--seconds", type=float, default=12)
    ap.add_argument("--shots", type=Path)
    a = ap.parse_args()
    os.environ.setdefault("ERGOSTAT_HOME", tempfile.mkdtemp(prefix="ergostat-demos-"))
    names = a.demos or sorted(p.name for p in DEMOS.iterdir() if (p / "ergostat.toml").exists())
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
