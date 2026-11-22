"""Walk a page in Chromium: a JSON list of steps run in one page, for a session to see what a person would.

    python scripts/walk.py STEPS [--shots DIR] [--size 1440x900] [--timeout MS]

STEPS is a JSON file, ``-`` for stdin, or the JSON itself. Each step is an object with one of these keys:
  {"goto": URL}  {"size": [W, H]}  {"dark": true}  {"wait": MS or SELECTOR}  {"click": SEL}  {"hover": SEL}
  {"fill": [SEL, TEXT]}  {"press": KEY or [SEL, KEY]}  {"scroll": [DX, DY] or SEL}  {"shot": NAME, "full": true}
  {"text": SEL}
A shot is written as DIR/NAME (DIR must exist; NAME matches SHOT_NAME); a text is printed cut at 6000 characters. A
step that fails is printed and the walk goes on; console errors and failed requests are printed at the end. Exit 0
when every step ran, 2 otherwise (and 2, with nothing run, for steps that are not well formed).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

KINDS = ("goto", "size", "dark", "wait", "click", "hover", "fill", "press", "scroll", "shot", "text")
SHOT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}\.png$")
TEXT_CAP = 6000
LOOPBACK = "127.0.0.1,localhost"


def launch_options(env: dict) -> dict:
    """Chromium's launch arguments: no proxy for loopback; HTTPS_PROXY (when set) for any other host."""
    url = env.get("HTTPS_PROXY") or env.get("https_proxy")
    if not url:
        return {"args": ["--no-proxy-server"]}
    u = urlsplit(url if "://" in url else f"http://{url}")
    proxy = {"server": f"{u.scheme}://{u.hostname}" + (f":{u.port}" if u.port else ""), "bypass": LOOPBACK}
    if u.username:
        proxy.update(username=unquote(u.username), password=unquote(u.password or ""))
    return {"proxy": proxy}


def kind_of(step) -> str:
    keys = [k for k in KINDS if isinstance(step, dict) and k in step]
    if len(keys) != 1:
        raise ValueError(f"a step needs exactly one of {', '.join(KINDS)}: {json.dumps(step)[:200]}")
    return keys[0]


def problems(steps, shots: Path | None) -> list[str]:
    """What makes the steps not run at all: not a list, a step of no kind, a shot with a bad name or no --shots."""
    if not isinstance(steps, list):
        return ["the steps must be a JSON list"]
    out = []
    for i, s in enumerate(steps, 1):
        try:
            k = kind_of(s)
        except ValueError as e:
            out.append(f"step {i}: {e}")
            continue
        if k == "shot" and not (isinstance(s["shot"], str) and SHOT_NAME.fullmatch(s["shot"])):
            out.append(f"step {i}: refused shot name {s['shot']!r} (it must match {SHOT_NAME.pattern})")
        elif k == "shot" and shots is None:
            out.append(f"step {i}: a shot needs --shots DIR")
        elif k == "dark" and not isinstance(s["dark"], bool):
            out.append(f"step {i}: dark must be true or false, not {json.dumps(s['dark'])}")
    return out


def run_step(pg, step: dict, kind: str, shots: Path | None) -> str | None:
    """One step on the page; what it prints, if anything."""
    v = step[kind]
    if kind == "goto":
        pg.goto(v)
    elif kind == "size":
        pg.set_viewport_size({"width": int(v[0]), "height": int(v[1])})
    elif kind == "dark":
        pg.emulate_media(color_scheme="dark" if v else "light")
    elif kind == "wait":
        pg.wait_for_timeout(float(v)) if isinstance(v, (int, float)) else pg.wait_for_selector(v)
    elif kind in ("click", "hover"):
        getattr(pg, kind)(v)
    elif kind == "fill":
        pg.fill(v[0], v[1])
    elif kind == "press":
        pg.press(v[0], v[1]) if isinstance(v, list) else pg.keyboard.press(v)
    elif kind == "scroll":
        pg.mouse.wheel(v[0], v[1]) if isinstance(v, list) else pg.locator(v).first.scroll_into_view_if_needed()
    elif kind == "shot":
        path = (shots / v).resolve()
        if path.parent != shots.resolve():
            raise ValueError(f"refused shot path {path}")
        pg.screenshot(path=str(path), full_page=bool(step.get("full")))
        return f"shot: {path}"
    elif kind == "text":
        t = pg.inner_text(v or "body")
        return t[:TEXT_CAP] + (f"\n[... cut at {TEXT_CAP} of {len(t)} characters]" if len(t) > TEXT_CAP else "")
    return None


def walk(steps: list, shots: Path | None, size: tuple[int, int], timeout: float, env: dict) -> int:
    from playwright.sync_api import sync_playwright
    failed, errors, requests = 0, [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options(env))
        try:
            pg = browser.new_page(viewport={"width": size[0], "height": size[1]})
            pg.set_default_timeout(timeout)
            pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(f"page: {e}"))
            pg.on("requestfailed", lambda r: requests.append(f"{r.method} {r.url}: {r.failure}"))
            for i, s in enumerate(steps, 1):
                kind = kind_of(s)
                try:
                    said = run_step(pg, s, kind, shots)
                    print(f"ok   {i} {kind}" + (f"\n{said}" if said else ""), flush=True)
                except Exception as e:           # a failed step is said and the walk goes on
                    failed += 1
                    print(f"FAIL {i} {kind}: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}", flush=True)
        finally:
            browser.close()
    print(f"console errors: {len(errors)}" + "".join(f"\n  {e}" for e in errors))
    print(f"failed requests: {len(requests)}" + "".join(f"\n  {r}" for r in requests))
    return 2 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("steps", help="a JSON file, - for stdin, or the JSON list itself")
    ap.add_argument("--shots", type=Path, help="the folder screenshots go to (it must exist)")
    ap.add_argument("--size", default="1440x900")
    ap.add_argument("--timeout", type=float, default=10000, help="milliseconds each step may take")
    a = ap.parse_args(argv)
    try:
        inline = a.steps.lstrip()[:1] in ("[", "{")
        steps = json.loads(sys.stdin.read() if a.steps == "-" else a.steps if inline else Path(a.steps).read_text())
        w, h = (int(x) for x in a.size.lower().split("x"))
    except (OSError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    bad = problems(steps, a.shots) + ([f"--shots {a.shots} is not a folder"] if a.shots and not a.shots.is_dir() else [])
    if bad:
        print("refused:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 2
    return walk(steps, a.shots, (w, h), a.timeout, dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())
