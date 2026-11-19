"""The layout rules (tests/layout_rules.py) run over a corpus of models: every example and the generated ones
(tests/diagram_corpus.py), every view (Dynamics, Blocks, Process), each drawn whole, everything open, each system
open, each system alone. Writes what was drawn and what each rule found, and a report.

    uv run --with playwright==1.63.0 python scripts/layout_corpus.py OUT [--examples a,b | --no-examples]
        [--generated N] [--seed 1] [--views dynamics,blocks,process] [--workers 3] [--shots worst|all|none]
        [--ports 8791,8793,8796] [--only MODEL,...]

OUT/geometry/<model>/<view>.json   the drawn geometry (scripts/layout_geometry.js)
OUT/shots/<model>/<view>.png       a screenshot of the canvas (with --shots all, or of the worst views)
OUT/findings.json                  every instance, by rule
OUT/report.md                      counts per rule and severity, and the worst instances with crops (OUT/crops/)

Ports are the 8790s only (8790 is never used). Each worker is its own process with its own Chromium; a watchdog
stops the run if the machine's threads pass 1,500 or this run's memory 6 GB."""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                    # (tests/layout_rules.py and tests/diagram_corpus.py, shared with the tests)

from tests import diagram_corpus as corpus  # noqa: E402
from tests import layout_rules as rules  # noqa: E402

GEOMETRY = (ROOT / "scripts" / "layout_geometry.js").read_text()
READY = ("() => typeof S !== 'undefined' && S.layout && S.graphSig && !S.layout.routing && "
         "document.querySelectorAll('svg.canvas g.node').length > 0")
EMPTY = ("() => typeof S !== 'undefined' && !!S.graph && !(S.graph.nodes || []).length && "
         "!!document.querySelector('.canvas-wrap .empty')")      # (nothing to draw: no goal, or no record)
READY_OR_EMPTY = f"() => ({READY[6:]}) || ({EMPTY[6:]})"
VIEWPORT = {"width": 1440, "height": 900}        # a typical laptop
MAX_THREADS, MAX_RSS_GB = 1500, 6.0


def port_free(p: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
            return True
        except OSError:
            return False


PORTS = [8791, 8792, 8793, 8794, 8795, 8796, 8797, 8798, 8799]     # (never 8790: the owner's)


def serve(d: Path, port: int, home: Path):
    """The project at d served on a free port of the 8790s (port first, if free): other runs share them, so
    one taken meanwhile is given up for the next. The server says where it listens (it walks up from a port
    taken): one outside the 8790s is stopped and another port tried."""
    import re as _re
    give_up, attempt = time.monotonic() + 900, -1      # (other runs hold them all at times: wait for one)
    while time.monotonic() < give_up:
        attempt += 1
        free = [p for p in dict.fromkeys([port, *PORTS]) if p != 8790 and port_free(p)]
        if not free:
            time.sleep(1)
            continue
        p = free[attempt % len(free)]
        py = str(Path(os.environ["LAYOUT_ENGINE"]) / ".venv" / "bin" / "python") if os.environ.get("LAYOUT_ENGINE") else sys.executable
        proc = subprocess.Popen([py, "-m", "ergostat", "-C", str(d), "web", "--port", str(p)], cwd=str(d.parent),   # (not here: -m
                                # would import the ergostat in the working directory, whatever the engine)
                                env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
        said: list[str] = []
        threading.Thread(target=lambda q=proc, w=said: w.extend(q.stdout), daemon=True).start()
        deadline = time.monotonic() + 60
        url = None
        while time.monotonic() < deadline and proc.poll() is None:
            m = next((_re.search(r"http://127\.0\.0\.1:(\d+)", x) for x in said if "http://" in x), None)
            if m:
                if not 8790 < int(m.group(1)) <= 8799:
                    break
                url = m.group(0)
                try:
                    urllib.request.urlopen(url + "/api/status", timeout=2)
                    return proc, url
                except Exception:
                    pass
            time.sleep(0.15)
        proc.kill()
        proc.wait(5)
        if url is None and time.monotonic() >= deadline:
            raise RuntimeError(f"{d.name}: the page never answered")
    raise RuntimeError(f"{d.name}: no free port in the 8790s")


def run_model(pg, name: str, src: Path, port: int, out: Path, views: list[str], shots: str, tmp: Path) -> list[dict]:
    """Every view of one model drawn and its geometry kept; returns [{model, view, error?}]."""
    d = tmp / name
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(src, d, ignore=shutil.ignore_patterns("run", "__pycache__", ".ergostat"))
    seeded = {}
    if "process" in views:
        try:
            seeded = corpus.seed_workflows(d, time.time())
        except Exception as e:                    # (a model with no items: no process map)
            seeded = {"_error": str(e)}
    proc, url = serve(d, port, tmp / "home")
    done = []
    try:
        time.sleep(0.3 if not seeded else 1.6)    # past the page's snapshot of the moment it started
        gdir = out / "geometry" / name
        gdir.mkdir(parents=True, exist_ok=True)
        i = 0
        for kind in views:
            if kind == "process":
                kinds = ",".join(k for k in seeded if not k.startswith("_"))
                queries = [f"view=process&kinds={kinds}", f"view=process&by=events&kinds={kinds}"] if kinds else []
            else:
                pg.goto(f"{url}/diagram?v={i}&view={kind}")
                i += 1
                try:
                    pg.wait_for_function(READY_OR_EMPTY, timeout=60000)
                    tree = pg.evaluate("() => S.graph.tree || {}")
                except Exception:
                    tree = {}
                queries = corpus.views_of(kind, tree, 1 if name.startswith("gen-") else None)
            for q in queries:
                i += 1
                tag = corpus.view_tag(q)
                rec = {"model": name, "view": tag}
                try:
                    pg.goto(f"{url}/diagram?v={i}&{q}", timeout=120000)
                    pg.wait_for_function(READY_OR_EMPTY, timeout=120000)
                    if pg.evaluate(EMPTY):
                        continue                          # (nothing to draw here: no goal, or no record)
                    pg.wait_for_timeout(150)
                    geo = pg.evaluate(GEOMETRY)
                    if not geo:
                        raise RuntimeError("nothing drawn")
                    geo.update(model=name, query=q)
                    (gdir / f"{tag}.json").write_text(json.dumps(geo))
                    if shots == "all":
                        (out / "shots" / name).mkdir(parents=True, exist_ok=True)
                        pg.locator("svg.canvas").screenshot(path=str(out / "shots" / name / f"{tag}.png"))
                except Exception as e:
                    rec["error"] = str(e).splitlines()[0][:200]
                done.append(rec)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return done


def worker(args) -> list[dict]:
    jobs, port, out, views, shots = args
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix=f"layout-{port}-"))
    os.environ["ERGOSTAT_HOME"] = str(tmp / "home")     # (the record seeded here is the one the page reads)
    recs = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for name, src in jobs:
                pg = b.new_page(viewport=VIEWPORT)
                errs = []
                pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
                t = time.monotonic()
                try:
                    got = run_model(pg, name, Path(src), port, Path(out), views, shots, tmp)
                except Exception as e:
                    got = [{"model": name, "view": "*", "error": str(e)[:200]}]
                for r in got:
                    r.setdefault("pageErrors", errs[:3])
                recs += got
                pg.close()
                print(f"[{port}] {name}: {len(got)} views, {time.monotonic() - t:.1f}s", flush=True)
            b.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return recs


def tree_use(me: int) -> tuple[int, float, int]:
    """This run's threads and memory (GB), its process and all below it; and the machine's threads."""
    per: dict[int, int] = {}
    for line in subprocess.run(["ps", "-M", "-A"], capture_output=True, text=True).stdout.splitlines()[1:]:
        t = line.split()
        if t:
            pid = t[0] if t[0].isdigit() else (t[1] if len(t) > 1 and t[1].isdigit() else None)
            if pid:
                per[int(pid)] = per.get(int(pid), 0) + 1
    kids: dict[int, list] = {}
    for line in subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss="], capture_output=True, text=True).stdout.splitlines():
        pid, ppid, kb = (int(x) for x in line.split())
        kids.setdefault(ppid, []).append((pid, kb))
    tree, todo, rss = {me}, [me], 0
    while todo:
        for pid, kb in kids.get(todo.pop(), []):
            if pid not in tree:
                tree.add(pid)
                rss += kb
                todo.append(pid)
    return sum(per.get(p, 0) for p in tree), rss / 1e6, sum(per.values())


def watchdog(stop: threading.Event) -> None:
    """Kills the run (every process below it) past MAX_THREADS threads of its own, or MAX_RSS_GB of memory, or the
    machine's threads grown by more than MAX_THREADS since it started."""
    me = os.getpid()
    base = tree_use(me)[2]
    while not stop.wait(4):
        try:
            threads, gb, machine = tree_use(me)
            if threads > MAX_THREADS or gb > MAX_RSS_GB or machine > base + MAX_THREADS:
                print(f"WATCHDOG: {threads} threads, {gb:.1f} GB, machine {machine} (from {base}): stopping", flush=True)
                out = subprocess.run(["pgrep", "-P", str(me)], capture_output=True, text=True).stdout.split()
                todo = [int(x) for x in out]
                while todo:
                    pid = todo.pop()
                    todo += [int(x) for x in subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()]
                    try:
                        os.kill(pid, 9)
                    except OSError:
                        pass
                os._exit(3)
        except Exception as e:                     # (never let the watchdog itself stop the run)
            print("watchdog:", e, flush=True)


def judge(out: Path) -> dict:
    """Every rule over every saved view: {rule: [instance, ...]}, each instance with its model and view."""
    found: dict[str, list] = {r.name: [] for r in rules.RULES}
    views = 0
    for f in sorted((out / "geometry").glob("*/*.json")):
        geo = json.loads(f.read_text())
        views += 1
        for inst in rules.check(geo):
            inst.update(model=geo["model"], view=f.stem, query=geo.get("query", ""))
            found[inst["rule"]].append(inst)
    return {"views": views, "found": found}


def crops(out: Path, worst: list[dict], port: int) -> None:
    """A screenshot of each worst instance's view, cropped round it (the model is served again for it)."""
    from playwright.sync_api import sync_playwright
    by_model: dict[str, list] = {}
    for inst in worst:
        by_model.setdefault(inst["model"], []).append(inst)
    tmp = Path(tempfile.mkdtemp(prefix="layout-crops-"))
    os.environ["ERGOSTAT_HOME"] = str(tmp / "home")
    srcs = dict(corpus.all_models(out / "models", 0, 0, examples=[]))
    (out / "crops").mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for model, insts in by_model.items():
                src = srcs.get(model) or (out / "models" / model)
                d = tmp / model
                shutil.copytree(src, d, ignore=shutil.ignore_patterns("run", "__pycache__", ".ergostat"))
                if any("process" in i["query"] for i in insts):
                    corpus.seed_workflows(d, time.time())
                proc, url = serve(d, port, tmp / "home")
                try:
                    time.sleep(1.6)
                    pg = b.new_page(viewport=VIEWPORT)
                    for n, inst in enumerate(insts):
                        pg.goto(f"{url}/diagram?v={n}&{inst['query']}")
                        pg.wait_for_function(READY, timeout=120000)
                        pg.wait_for_timeout(200)
                        z = pg.evaluate("() => { const r = document.querySelector('svg.canvas').getBoundingClientRect(); "
                                        "return [S.view.k, S.view.x, S.view.y, r.left, r.top]; }")
                        k, vx, vy, cl, ct = z
                        x0, y0, x1, y1 = inst["box"]
                        pad = 60
                        clip = {"x": max(0, cl + vx + (x0 - pad) * k), "y": max(0, ct + vy + (y0 - pad) * k)}
                        clip["width"] = max(40, min(VIEWPORT["width"] - clip["x"], (x1 - x0 + 2 * pad) * k))
                        clip["height"] = max(40, min(VIEWPORT["height"] - clip["y"], (y1 - y0 + 2 * pad) * k))
                        path = out / "crops" / f"{inst['rule']}--{model}--{inst['view']}--{n}.png"
                        try:
                            if clip["x"] >= VIEWPORT["width"] - 40 or clip["y"] >= VIEWPORT["height"] - 40:
                                raise ValueError("off the screen")
                            pg.screenshot(path=str(path), clip=clip)
                            inst["crop"] = str(path.relative_to(out))
                        except Exception as e:      # (beyond the screen at the fitted zoom: no crop)
                            inst["crop_error"] = str(e).splitlines()[0][:80]
                    pg.close()
                finally:
                    proc.terminate()
                    proc.wait(10)
            b.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def report(out: Path, judged: dict, recs: list[dict], per_rule: int) -> list[dict]:
    found = judged["found"]
    lines = ["# Layout rules over the corpus\n", f"{judged['views']} views of "
             f"{len({r['model'] for r in recs}) or '?'} models; {sum(1 for r in recs if r.get('error'))} views failed to draw.\n",
             "| rule | severity | instances | views | worst |", "|---|---|---|---|---|"]
    worst = []
    for r in rules.RULES:
        xs = sorted(found[r.name], key=lambda i: -i["score"])
        lines.append(f"| {r.name} | {r.severity} | {len(xs)} | {len({(i['model'], i['view']) for i in xs})} | "
                     f"{xs[0]['score'] if xs else ''} |")
        seen = set()
        for i in xs:
            if (i["model"], i["view"]) in seen:
                continue
            seen.add((i["model"], i["view"]))
            worst.append(i)
            if len(seen) >= per_rule:
                break
    lines.append("\n## Worst instances\n")
    for i in worst:
        lines.append(f"- **{i['rule']}** {i['model']} [{i['view']}] {i['what']} (score {i['score']})"
                     + (f" ![]({i['crop']})" if i.get("crop") else ""))
    errs = [r for r in recs if r.get("error")]
    if errs:
        lines.append("\n## Views that failed to draw\n")
        lines += [f"- {r['model']} [{r['view']}]: {r['error']}" for r in errs[:50]]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return worst


def compare(before: Path, after: Path) -> str:
    """Counts per rule and severity, before and after, over the views both drew (a markdown table)."""
    b, a = json.loads((before / "findings.json").read_text()), json.loads((after / "findings.json").read_text())
    views = lambda d: {f"{p.parent.name}/{p.stem}" for p in (d / "geometry").glob("*/*.json")}     # noqa: E731
    both = views(before) & views(after)
    rows = ["| rule | severity | before | after | change |", "|---|---|---|---|---|"]
    for r in rules.RULES:
        for sev in ("critical", "major", "minor"):
            nb = sum(1 for i in b.get(r.name, []) if i["severity"] == sev and f"{i['model']}/{i['view']}" in both)
            na = sum(1 for i in a.get(r.name, []) if i["severity"] == sev and f"{i['model']}/{i['view']}" in both)
            if nb or na:
                rows.append(f"| {r.name} | {sev} | {nb} | {na} | {na - nb:+d} |")
    return f"{len(both)} views drawn both times.\n\n" + "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--examples", default="all")
    ap.add_argument("--no-examples", action="store_true")
    ap.add_argument("--generated", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--views", default="dynamics,blocks,process")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--shots", default="worst", choices=["worst", "all", "none"])
    ap.add_argument("--ports", default="8791,8793,8796")
    ap.add_argument("--only", default="")
    ap.add_argument("--engine", default="", help="draw with the ergostat at this checkout, by its own .venv (a before for a comparison)")
    ap.add_argument("--compare", default="", help="with --judge-only: OUT/compare.md, counts per rule against this run")
    ap.add_argument("--judge-only", action="store_true", help="judge the geometry already in OUT again")
    ap.add_argument("--worst", type=int, default=4, help="worst views shown per rule")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.engine:
        os.environ["LAYOUT_ENGINE"] = str(Path(a.engine).resolve())      # (the workers and their servers inherit it)
    recs: list[dict] = []
    if not a.judge_only:
        examples = None if a.no_examples else ([] if a.examples == "all" else a.examples.split(","))
        models = corpus.all_models(out / "models", a.generated, a.seed, examples=examples)
        if a.only:
            models = [m for m in models if m[0] in a.only.split(",")]
        ports = [int(p) for p in a.ports.split(",") if 8790 < int(p) <= 8799]   # (each worker's first choice)
        n = max(1, min(a.workers, len(models)))
        ports = (ports * n)[:n]
        print(f"{len(models)} models, {n} workers on ports {ports[:n]}", flush=True)
        jobs = [[] for _ in range(n)]
        for i, m in enumerate(sorted(models, key=lambda m: -corpus.weight(m[1]))):
            jobs[i % n].append((m[0], str(m[1])))
        stop = threading.Event()
        threading.Thread(target=watchdog, args=(stop,), daemon=True).start()
        views = a.views.split(",")
        t = time.monotonic()
        with mp.get_context("spawn").Pool(n) as pool:
            for got in pool.imap_unordered(worker, [(jobs[i], ports[i], str(out), views, a.shots) for i in range(n)]):
                recs += got
        stop.set()
        (out / "runs.json").write_text(json.dumps(recs, indent=0))
        print(f"drawn in {time.monotonic() - t:.0f}s", flush=True)
    elif (out / "runs.json").exists():
        recs = json.loads((out / "runs.json").read_text())
    judged = judge(out)
    worst = report(out, judged, recs, a.worst)
    if a.shots != "none" and worst:
        crops(out, worst, int(a.ports.split(",")[0]))
        report(out, judged, recs, a.worst)        # (again, with the crops)
    (out / "findings.json").write_text(json.dumps({k: v for k, v in judged["found"].items()}, indent=0))
    if a.compare:
        (out / "compare.md").write_text(compare(Path(a.compare), out))
        print((out / "compare.md").read_text())
    print((out / "report.md").read_text().split("## Worst")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
