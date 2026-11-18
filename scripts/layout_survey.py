"""The diagram's layout compared across settings: every example, every view, each layout named on the
command line (the page's ?layout= switch: layouts.js ELK_PRESETS, "elk" for ELK as diagram.js sets it,
none for the default), measured by the audit (size, empty share, fit zoom, crossings, bends, lines
through parts, parts on parts) and timed; a screenshot of each view asked for with --shots (or all).

    uv run --with playwright python scripts/layout_survey.py OUT [--layouts a,b] [--examples x,y]
        [--shots image-squeeze:system=lab,...] [--port 8795]

Writes OUT/results.json and OUT/<layout>/<example>__<view>.png."""
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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUDIT = (ROOT / "scripts" / "diagram_audit.js").read_text()
READY = ("() => typeof S !== 'undefined' && S.layout && S.graphSig && !S.layout.routing && "
         "document.querySelectorAll('svg.canvas g.node').length > 0")
TIMED = ("async () => { const t = performance.now(); const lay = await layoutGraph(S.graph, 1.6, false); "
         "const first = performance.now() - t; await lay.whenRouted; return [first, performance.now() - t]; }")


def serve(name: str, tmp: Path, port: int):
    d = tmp / name
    shutil.copytree(ROOT / "examples" / name, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            return proc, url
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit(f"{name}: no answer")


def summary(results: dict, base: str = "default") -> None:
    """Per layout, over the views every layout drew: the geometric mean of the drawing's area and of the
    fit zoom, the views that fit at legible zoom (0.7), the worst aspect, and the audit's faults, summed."""
    import math
    keys = set.intersection(*(set(k for k, r in v.items() if "error" not in r) for v in results.values()))

    def gm(xs):
        return math.exp(sum(math.log(max(x, 1e-6)) for x in xs) / max(1, len(xs)))

    print(f"{len(keys)} views in common")
    print(f"{'layout':26} {'area':>8} {'fit':>6} {'>=.7':>5} {'aspect':>7} {'empty':>6} {'cross':>6} {'bends':>6} "
          f"{'thru':>5} {'ovl':>4} {'detr':>5} {'net':>4} {'parts':>5} {'pipe>6':>6}")
    for lay, rows in sorted(results.items(), key=lambda kv: -gm([kv[1][k]["fit"] for k in keys])):
        rs = [rows[k] for k in keys]
        print(f"{lay:26} {gm([r['width'] * r['height'] for r in rs]) / 1e6:8.2f} {gm([r['fit'] for r in rs]):6.3f} "
              f"{sum(r['fit'] >= 0.7 for r in rs):5d} {max(max(r['aspect'], 1 / r['aspect']) for r in rs):7.1f} "
              f"{sum(r['empty'] for r in rs) / len(rs):6.3f} {sum(r['crossings'] for r in rs):6d} "
              f"{sum(r['pipeBends'] + r['infoBends'] for r in rs):6d} {sum(r['through'] for r in rs):5d} "
              f"{sum(r['overlap'] for r in rs):4d} {sum(r['detour'] for r in rs):5d} {sum(r['netCrossings'] for r in rs):4d} "
              f"{sum(r.get('partOverlap', 0) for r in rs):5d} "
              f"{sum(r['mostPipeBends'] > 6 for r in rs):6d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--layouts", default="")
    ap.add_argument("--examples", default="")
    ap.add_argument("--shots", default="")
    ap.add_argument("--port", type=int, default=8795)
    ap.add_argument("--no-time", action="store_true")
    ap.add_argument("--viewport", default="1600x1000", help="the window, WxH (the layout follows its shape)")
    ap.add_argument("--summary", action="store_true", help="only summarise OUT/results.json")
    a = ap.parse_args()
    if a.summary:
        summary(json.loads((Path(a.out) / "results.json").read_text()))
        return
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    layouts = a.layouts.split(",") if a.layouts else [""]
    examples = a.examples.split(",") if a.examples else sorted(p.name for p in (ROOT / "examples").iterdir()
                                                                if (p / "ergostat.yaml").exists())
    shots = {tuple(s.split(":", 1)) for s in a.shots.split(",") if s} if a.shots != "all" else "all"
    res_path = out / "results.json"
    results = json.loads(res_path.read_text()) if res_path.exists() else {}
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmpd:
        b = p.chromium.launch(channel="chrome")
        for ex in examples:
            proc, url = serve(ex, Path(tmpd), a.port)
            try:
                for lay in layouts:
                    vw, vh = map(int, a.viewport.split("x"))
                    pg = b.new_page(viewport={"width": vw, "height": vh})
                    errors: list[str] = []
                    pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                    q = f"layout={lay}&" if lay else ""
                    pg.goto(f"{url}/diagram?{q}v=0")
                    pg.wait_for_function(READY, timeout=20000)
                    tree = pg.evaluate("() => S.graph.tree || {}")
                    views = ["", "open=*", *(f"open={s}" for s in tree), *(f"system={s}" for s in tree)]
                    for i, v in enumerate(views):
                        pg.goto(f"{url}/diagram?{q}v={i + 1}" + (f"&{v}" if v else ""))
                        try:
                            pg.wait_for_function(READY, timeout=20000)
                        except Exception as e:
                            results.setdefault(lay or "default", {})[f"{ex}|{v}"] = {"error": str(e)[:200]}
                            continue
                        r = pg.evaluate(AUDIT)
                        first, final = (0, 0) if a.no_time else pg.evaluate(TIMED)
                        if not a.no_time:
                            pg.wait_for_function(READY, timeout=20000)
                        row = {**r["size"], "through": len(r["through"]), "overlap": len(r["overlap"]),
                               "detour": len(r["detour"]), "netCrossings": len(r["netCrossings"]), "partOverlap": len(r["partOverlap"]),
                               "crossings": r["crossings"], "pipeBends": r["pipeBends"], "infoBends": r["infoBends"],
                               "mostPipeBends": r["mostPipeBends"][0], "first": round(first), "routed": round(final),
                               "errors": errors[:3]}
                        results.setdefault(lay or "default", {})[f"{ex}|{v}"] = row
                        print(f"{lay or 'default'} {ex} [{v or 'whole'}] {row['width']}x{row['height']} empty {row['empty']} "
                              f"fit {row['fit']} x{row['crossings']} bends {row['pipeBends']}/{row['infoBends']} "
                              f"through {row['through']} overlap {row['overlap']} detour {row['detour']} "
                              f"net {row['netCrossings']} parts {row['partOverlap']} {row['first']}/{row['routed']}ms", flush=True)
                        if shots == "all" or (ex, v) in shots:
                            pg.get_by_role("button", name="fit").click()
                            pg.wait_for_timeout(150)
                            d = out / (lay or "default")
                            d.mkdir(exist_ok=True)
                            pg.screenshot(path=str(d / f"{ex}__{v.replace('=', '-').replace('*', 'all') or 'whole'}.png"))
                    pg.close()
            finally:
                proc.terminate()
                proc.wait(10)
                res_path.write_text(json.dumps(results, indent=1))
        b.close()


if __name__ == "__main__":
    main()
