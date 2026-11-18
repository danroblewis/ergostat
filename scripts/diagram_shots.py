"""Screenshots of a project's two diagrams, for an agent that can read images (the authoring bench's "may look"
round): the stock-and-flow view and the control view, each of the whole model with every system open, or of one
system.

    uv run --with playwright python scripts/diagram_shots.py PROJECT OUT_DIR [--system NAME] [--port 8795]

Starts ``ergostat web`` on the port for the project, writes OUT_DIR/dynamics.png and OUT_DIR/blocks.png, and stops
it. Drives the Chrome installed on this machine."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("out")
    ap.add_argument("--system")
    ap.add_argument("--port", type=int, default=8795)
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    web = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", a.project, "web", "--port", str(a.port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
    url = f"http://127.0.0.1:{a.port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        q = f"system={a.system}" if a.system else "open=*"
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome")
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            for view in ("dynamics", "blocks"):
                pg.goto(f"{url}/diagram?view={view}&{q}")
                pg.wait_for_timeout(4500)
                pg.screenshot(path=str(out / f"{view}.png"))
                print(out / f"{view}.png")
            b.close()
    finally:
        web.terminate()
        web.wait(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
