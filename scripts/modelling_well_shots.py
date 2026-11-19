"""The screenshots of docs/MODELLING-WELL.md: the alert-triage example (good) and its deliberately poor model, each
run from a fresh copy on its stand-ins for a while, then each view shot small; and two shots of the examples it
cites (the coordinator's cascade, the ticket factory's process map).

    uv run --with playwright python scripts/modelling_well_shots.py [--seconds 90] [--port 8795]

Writes docs/screenshots/modelling-well/*.png. Drives the Chrome installed on this machine."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "modelling-well"
PY = [sys.executable, "-m", "ergostat"]


def up(url: str) -> None:
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"{url} did not answer")


def shoot(url: str, shots: list[tuple[str, str, tuple[int, int]]], scale: float = 0.7, clip: dict | None = None) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        w, h = shots[0][2]
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)     # small files
        pg.add_init_script("try { localStorage.setItem('ergostat.loops', '0'); "            # no loop markers,
                           "localStorage.setItem('ergostat.side', 'hidden'); } catch (e) {}")   # no side panel
        for name, query, _ in shots:
            pg.goto(f"{url}/diagram?{query}")
            pg.wait_for_timeout(5000)
            try:
                pg.get_by_role("button", name="Fit", exact=True).click(timeout=2000)
                pg.wait_for_timeout(1500)
            except Exception:                              # (the Process view fits itself)
                pass
            pg.screenshot(path=str(OUT / f"{name}.png"), clip=clip)
            print(OUT / f"{name}.png", flush=True)
        b.close()


def run(project: Path, home: Path, port: int, seconds: float, shots, env_extra=None, **how) -> None:
    env = {**os.environ, "ERGOSTAT_HOME": str(home), **(env_extra or {})}
    subprocess.run([*PY, "-C", str(project), "run", "--port", str(port)], env=env, check=True, capture_output=True)
    try:
        up(f"http://127.0.0.1:{port}")
        time.sleep(seconds)
        shoot(f"http://127.0.0.1:{port}", shots, **how)
    finally:
        subprocess.run([*PY, "-C", str(project), "run", "--stop"], env=env, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=90)
    ap.add_argument("--port", type=int, default=8795)
    ap.add_argument("--only", help="good, poor, coordinator, factory (commas)")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else {"good", "poor", "coordinator", "factory"}
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mw-shots-"))
    small = (1400, 860)
    try:
        shutil.copytree(ROOT / "examples" / "alert-triage", tmp / "alert-triage",
                        ignore=shutil.ignore_patterns("run", "__pycache__"))
        if "good" in only:
            run(tmp / "alert-triage", tmp / "home", a.port, a.seconds, [
                ("good-dynamics", "view=dynamics&open=*", small),
                ("good-blocks", "view=blocks&system=alerts", small),
                ("good-process", "view=process", small),
            ])
        if "poor" in only:
            run(tmp / "alert-triage" / "poor", tmp / "home", a.port, a.seconds, [
                ("poor-dynamics", "view=dynamics", small),
                ("poor-blocks", "view=blocks", small),
                ("poor-process", "view=process", small),
            ])
        if "coordinator" in only:
            shutil.copytree(ROOT / "examples" / "coordinator", tmp / "coordinator",
                            ignore=shutil.ignore_patterns("run", "__pycache__"))
            run(tmp / "coordinator", tmp / "home", a.port, 20, [
                ("coordinator-blocks", "view=blocks&system=work", small)])
        if "factory" in only:
            shutil.copytree(ROOT / "examples" / "ticket-factory", tmp / "ticket-factory",
                            ignore=shutil.ignore_patterns("run", "__pycache__", "factory.conf"))
            run(tmp / "ticket-factory", tmp / "home", a.port, a.seconds, [
                ("factory-process", "view=process&kinds=ticket", small)], {"TF_OFFLINE": "1"},
                scale=1.4, clip={"x": 640, "y": 400, "width": 760, "height": 150})   # its review and CI rework, close
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
