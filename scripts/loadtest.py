"""A load test of the record (docs/proposals/harness-parity-plan.md, F2): what grows and what breaks
when image-squeeze and the-job run for a long time.

Each demo runs for real for a while (its stand-ins, at the speed its simulated world already runs),
and that record is the template. A long record is then written with the stores' bulk writers: the
template tiled end to end until it covers ``--days`` (each tile's events get their own ids; most
items get a new id per tile, as new work arrives, and one in four keeps its id, so some items
collect a long history; the benchmark's cases keep theirs). Then the page's server is started on
that record and every page's API is asked for, at the page's window and at longer ones: the time
each answer takes, its size, the server's memory. Last, the demo itself runs on top of the long
record for a while, to see whether the engine keeps up.

    uv run python scripts/loadtest.py [--days 1,7,30] [--capture 120] [--live 60] [--out DIR] [demo ...]
    uv run python scripts/loadtest.py --compare before/results.json after/results.json

The result is ``DIR/results.json`` and a table on stdout. Ports are the server's own choice (set
ERGOSTAT's web port range from outside when several agents share the machine)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DEMOS = ROOT / "examples"
ERGOSTAT = [sys.executable, "-m", "ergostat"]
KEEP_IDS = ("case/",)                 # items that are the same thing every tile (the benchmark's cases)
ONCE = ("model.changed", "ergostat.started", "ergostat.model-change.made", "ergostat.model-change.checked")


def sh(*args, env=None, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run([*ERGOSTAT, *args], capture_output=True, text=True, timeout=timeout, env=env)


def fresh_copy(demo: Path, where: Path) -> Path:
    dest = where / demo.name
    if dest.exists():
        shutil.rmtree(dest)
    got = subprocess.run(["git", "-C", str(demo), "ls-files"], capture_output=True, text=True)
    if got.returncode != 0:                 # not in a repository (an exported copy): the tree, less what runs write
        shutil.copytree(demo, dest, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__"))
        return dest
    for f in got.stdout.split():
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo / f, dest / f)
    return dest


def env_with(home: Path) -> dict:
    return {**os.environ, "ERGOSTAT_HOME": str(home)}


def project(copy: Path, home: Path):
    os.environ["ERGOSTAT_HOME"] = str(home)
    from ergostat import model as mdl
    from ergostat.store import Project
    return Project(mdl.load(copy))


def dir_size(d: Path) -> dict:
    out: dict[str, int] = {}
    for f in d.rglob("*"):
        if f.is_file():
            top = f.relative_to(d).parts[0]
            key = top if f.parent == d else top + "/"
            out[key] = out.get(key, 0) + f.stat().st_size
    return out


def store_bytes(d: Path) -> dict:
    sizes = dir_size(d)
    ev = sum(v for k, v in sizes.items() if k.startswith("events"))
    me = sum(v for k, v in sizes.items() if k.startswith("measurements"))
    return {"events_bytes": ev, "measurements_bytes": me, "all_bytes": sum(sizes.values()), "files": sizes}


# ---- 1. the template: the demo, run for real

def capture(demo: str, seconds: float, work: Path) -> tuple[Path, Path]:
    copy = fresh_copy(DEMOS / demo, work / "template")
    home = work / "template-home"
    env = env_with(home)
    r = sh("-C", str(copy), "run", env=env)
    if r.returncode != 0:
        raise SystemExit(f"{demo}: run failed: {r.stderr}")
    try:
        time.sleep(seconds)
    finally:
        sh("-C", str(copy), "run", "--stop", env=env)
    return copy, home


def read_template(p) -> tuple[list[dict], dict[str, list[tuple[float, float]]], float, float]:
    evs = p.events.query(n=None)
    series = {s["series"]: p.measurements.range(s["series"], 0, time.time() + 3600) for s in p.measurements.series()}
    times = [e["time"] for e in evs] + [t for pts in series.values() for t, _ in pts]
    return evs, series, min(times), max(times)


# ---- 2. the long record

def tiled_id(item: str | None, k: int) -> str | None:
    if not item or "/" not in item or k == 0 or item.startswith(KEEP_IDS) or zlib.crc32(item.encode()) % 4 == 0:
        return item
    return f"{item}-t{k}"


def _add(p, batch: list[dict]) -> int:
    import inspect
    if "new" in inspect.signature(p.events.add_many).parameters:     # a record written whole: no id is looked for
        return p.events.add_many(batch, new=True)
    return p.events.add_many(batch)


def with_storage(copy: Path, storage: str | None) -> None:
    """The copy's ergostat.yaml, with a ``storage:`` section (YAML, as given) when one is asked for."""
    if storage:
        y = copy / "ergostat.yaml"
        y.write_text(y.read_text() + "\nstorage:\n" + "".join(f"  {line}\n" for line in storage.splitlines()))


def compact(copy: Path, home: Path) -> dict:
    """``ergostat compact``, timed: the roll-up, keep, and the measurements' tiers."""
    t = time.time()
    r = sh("-C", str(copy), "compact", "--json", env=env_with(home), timeout=7200)
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout)[-2000:], "seconds": time.time() - t}
    return {**json.loads(r.stdout), "seconds": time.time() - t}


def synthesize(p, evs, series, t0: float, t1: float, days: float, end: float, chunk: int = 50000) -> dict:
    span = max(t1 - t0, 1.0)
    tiles = max(1, int(days * 86400 // span))
    start = end - tiles * span
    began = time.time()
    n_ev = n_me = 0
    batch: list[dict] = []
    rows: list[tuple[str, float, float]] = []
    for k in range(tiles):
        shift = start + k * span - t0
        for e in evs:
            if k and e["type"] in ONCE:
                continue
            batch.append({"id": f"{e['id']}-{k}" if k else e["id"], "at": e["time"] + shift, "type": e["type"],
                          "item": tiled_id(e.get("item"), k), "source": e.get("source"),
                          "causedby": (f"{e['causedby']}-{k}" if k else e["causedby"]) if e.get("causedby") else None,
                          "data": e.get("data")})
        for s, pts in series.items():
            rows += [(s, t + shift, v) for t, v in pts]
        if len(batch) >= chunk:
            n_ev += _add(p, batch)
            batch = []
        if len(rows) >= chunk * 4:
            p.measurements.add_many(rows)
            n_me += len(rows)
            rows = []
    if batch:
        n_ev += _add(p, batch)
    if rows:
        p.measurements.add_many(rows)
        n_me += len(rows)
    return {"tiles": tiles, "tile_seconds": span, "events": n_ev, "measurements": n_me, "write_seconds": time.time() - began,
            "start": start, "end": end}


# ---- 3. the page's server, asked for everything

def rss_kb(pid: int) -> int:
    r = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def ask(url: str, timeout: float) -> dict:
    t = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()
            return {"status": r.status, "seconds": time.time() - t, "bytes": len(body)}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "seconds": time.time() - t, "bytes": len(e.read() or b""), "error": str(e)}
    except Exception as e:              # noqa: BLE001 - a timeout is a result here
        return {"status": None, "seconds": time.time() - t, "bytes": 0, "error": f"{type(e).__name__}: {e}"}


def paths(p) -> list[tuple[str, str]]:
    """Every page's API, as the page asks for it: (name, path)."""
    m = p.model
    spec = getattr(m, "spec", None)
    out = [("status", "status"), ("graph", "graph"), ("graph dynamics", "graph?view=dynamics"),
           ("graph blocks", "graph?view=blocks"), ("graph wiring", "graph?view=wiring"), ("loops", "loops"),
           ("agents", "agents"), ("parts", "parts"), ("residuals", "residuals"),
           ("record", "events?n=200"), ("record (window)", "events?n=200&window=1"),
           ("items", "items")]
    if m.controllers:
        g = sorted(m.controllers)[0]
        out += [("loop", f"loops/{quote(g)}"), ("loop-scope", f"loop-scope?goal={quote(g)}"),
                ("loop-control", f"loop-control?goal={quote(g)}")]
    if m.agents:
        out.append(("agent", f"agents/{quote(sorted(m.agents)[0])}"))
    refs = [f"{'auxiliary' if s.auxiliary else 'stock'}.{n}" for n, s in m.stocks.items()] + [f"flow.{n}" for n in m.flows]
    out.append(("series (every part)", "series?refs=" + quote(",".join(refs))))
    out.append(("series (one, strip)", "series?strip=1&refs=" + quote(refs[0])))
    if spec is not None and spec.items:
        for k in sorted(spec.items)[:3]:
            out.append((f"items-flow {k}", f"items-flow?kind={quote(k)}"))
        out.append(("fit", "fit"))
        out.append(("dominance", "dominance"))
    biggest = next(iter(sorted(p.events.items(), key=lambda i: -i["n"])), None)
    if biggest:
        out.append((f"item ({biggest['n']} events)", f"items/{quote(biggest['item'], safe='')}"))
    return out


def serve_and_ask(copy: Path, home: Path, p, windows: list[str], timeout: float) -> dict:
    env = env_with(home)
    (p.dir / "web.json").unlink(missing_ok=True)
    proc = subprocess.Popen([*ERGOSTAT, "-C", str(copy), "web"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        url = None
        for _ in range(300):
            if (p.dir / "web.json").exists():
                url = json.loads((p.dir / "web.json").read_text())["url"]
                break
            time.sleep(0.1)
        if url is None:
            raise SystemExit(f"the server never started: {proc.stderr.read() if proc.poll() is not None else ''}")
        idle = rss_kb(proc.pid)
        out = {"rss_idle_kb": idle, "answers": []}
        peak = idle
        for w in windows:
            for name, path in paths(p):
                sep = "&" if "?" in path else "?"
                got = ask(f"{url}/api/{path}{sep}since={w}", timeout)
                got.update(api=name, window=w)
                rss = rss_kb(proc.pid)
                peak = max(peak, rss)
                got["rss_kb"] = rss
                out["answers"].append(got)
                print(f"    {w:>4} {name:<28} {got['seconds']:7.2f}s {got['bytes'] / 1024:9.1f} KB "
                      f"{got['status'] or got.get('error', '')}", flush=True)
        out["rss_peak_kb"] = peak
        return out
    finally:
        proc.terminate()
        try:
            _, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, err = proc.communicate()
        tb = err.count("Traceback")
        if tb:
            print(f"    the server wrote {tb} tracebacks: {err.strip().splitlines()[-1]}", flush=True)


# ---- 4. the demo, running on the long record

def live(copy: Path, home: Path, p, seconds: float) -> dict:
    env = env_with(home)
    ev0, me0 = p.events.count(), p.measurements.count()
    r = sh("-C", str(copy), "run", "--no-web", env=env)
    if r.returncode != 0:
        return {"error": r.stderr}
    try:
        time.sleep(seconds)
    finally:
        sh("-C", str(copy), "run", "--stop", env=env)
    log = (p.dir / "run.log").read_text(errors="replace") if (p.dir / "run.log").exists() else ""
    return {"seconds": seconds, "events": p.events.count() - ev0, "measurements": p.measurements.count() - me0,
            "log_errors": sum(1 for line in log.splitlines() if "Error" in line or "Traceback" in line)}


def _after(r: dict, k: str) -> str:
    return f"{r['compacted'][k] / 1e6:.1f}" if r.get("compacted") else "-"


def _rate(r: dict, k: str) -> str:
    return f"{r['live'][k] / r['live']['seconds']:.2f}" if r.get("live") and k in r["live"] else "-"


def compare(paths: list[Path]) -> int:
    """Results side by side: per demo and length, the stores' sizes, the roll-up, the engine's rate,
    and every answer's time and size, one column per results file."""
    rs = [json.loads(p.read_text()) for p in paths]
    print("columns: " + " | ".join(str(p) for p in paths))
    for demo in rs[0]["demos"]:
        for run in rs[0]["demos"][demo]["runs"]:
            runs = [next((x for x in r["demos"].get(demo, {}).get("runs", []) if x["days"] == run["days"]), None) for r in rs]
            print(f"\n## {demo}, {run['days']:g} days ({run['events']} events, {run['measurements']} readings written)")

            def row(name, f, runs=runs):
                print(f"{name:<34}" + " | ".join(f"{f(r):>18}" if r else f"{'-':>18}" for r in runs))
            row("events MB (as written)", lambda r: f"{r['events_bytes'] / 1e6:.1f}")
            row("measurements MB (as written)", lambda r: f"{r['measurements_bytes'] / 1e6:.1f}")
            row("compact s", lambda r: f"{r['compact']['seconds']:.0f}" if r.get("compact") else "-")
            row("events MB after compact", lambda r: _after(r, "events_bytes"))
            row("measurements MB after compact", lambda r: _after(r, "measurements_bytes"))
            row("archive MB", lambda r: f"{r['compact'].get('archive_bytes', 0) / 1e6:.1f}" if r.get("compact") else "-")
            row("server RSS peak MB", lambda r: f"{r['server']['rss_peak_kb'] / 1024:.0f}")
            row("live events/s", lambda r: _rate(r, "events"))
            row("live readings/s", lambda r: _rate(r, "measurements"))
            keys = [(a["window"], a["api"]) for a in run["server"]["answers"]]
            for w, api in keys:
                def cell(r, w=w, api=api):
                    a = next((x for x in r["server"]["answers"] if x["window"] == w and (x["api"] == api or
                              (api.startswith("item (") and x["api"].startswith("item (")))), None)
                    if a is None:
                        return "-"
                    if a["status"] != 200:
                        return "timeout" if "timed out" in (a.get("error") or "") else str(a["status"] or a.get("error", "")[:12])
                    return f"{a['seconds']:.2f}s {a['bytes'] / 1024:.0f}KB"
                row(f"{w} {api[:30]}", cell)
    return 0


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--compare":
        return compare([Path(x) for x in sys.argv[2:]])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("demos", nargs="*", default=["image-squeeze", "the-job"])
    ap.add_argument("--days", default="1,7,30", help="how long each long record is, comma separated")
    ap.add_argument("--capture", type=float, default=120, help="seconds each demo runs for its template")
    ap.add_argument("--live", type=float, default=60, help="seconds the demo runs on the long record (0: not at all)")
    ap.add_argument("--windows", default="1h,1d,30d", help="the page windows asked for")
    ap.add_argument("--timeout", type=float, default=60, help="a client's patience, seconds")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep", action="store_true", help="keep the long records")
    ap.add_argument("--storage", help="a storage: section for the long records (YAML, newlines as \\n), e.g. "
                                      "'events: segments\\nmeasurements: {backend: victoriametrics, url: http://127.0.0.1:8428}'")
    ap.add_argument("--no-compact", action="store_true", help="ask the long record as written, without ergostat compact")
    a = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="ergostat-load-"))
    out_dir = a.out or work
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {"started": time.time(), "demos": {}}
    for demo in a.demos:
        print(f"{demo}: capturing {a.capture:g}s of its record", flush=True)
        copy, thome = capture(demo, a.capture, work)
        tp = project(copy, thome)
        evs, series, t0, t1 = read_template(tp)
        rate = {"events_per_s": len(evs) / max(t1 - t0, 1), "measurements_per_s": sum(map(len, series.values())) / max(t1 - t0, 1)}
        print(f"  template: {len(evs)} events, {sum(map(len, series.values()))} readings in {t1 - t0:.0f}s", flush=True)
        results["demos"][demo] = {"template": {"events": len(evs), "series": len(series), "seconds": t1 - t0, **rate}, "runs": []}
        for days in [float(x) for x in a.days.split(",")]:
            home = work / f"home-{demo}-{days:g}d"
            long_copy = fresh_copy(DEMOS / demo, work / f"long-{days:g}d")
            with_storage(long_copy, (a.storage or "").replace("\\n", "\n"))
            p = project(long_copy, home)
            print(f"  {days:g} days: writing", flush=True)
            made = synthesize(p, evs, series, t0, t1, days, time.time())
            run = {"days": days, "storage": a.storage, **made, **store_bytes(p.dir)}
            print(f"    {made['events']} events, {made['measurements']} readings in {made['write_seconds']:.0f}s; "
                  f"events {run['events_bytes'] / 1e6:.1f} MB, measurements {run['measurements_bytes'] / 1e6:.1f} MB", flush=True)
            if not a.no_compact:
                run["compact"] = cp = compact(long_copy, home)
                p = project(long_copy, home)
                run["compacted"] = {**store_bytes(p.dir), "events": p.events.count(), "measurements": p.measurements.count()}
                ro = cp.get("rollup") or {}
                print(f"    compact: {cp['seconds']:.0f}s, rolled up {ro.get('events', 0)} events of {ro.get('items', 0)} items; "
                      f"now events {run['compacted']['events_bytes'] / 1e6:.1f} MB ({run['compacted']['events']}), "
                      f"measurements {run['compacted']['measurements_bytes'] / 1e6:.1f} MB ({run['compacted']['measurements']} rows), "
                      f"archive {cp.get('archive_bytes', 0) / 1e6:.1f} MB" + (f"; {cp['error'][-300:]}" if "error" in cp else ""),
                      flush=True)
            run["server"] = serve_and_ask(long_copy, home, p, a.windows.split(","), a.timeout)
            if a.live:
                print(f"    running the demo on it for {a.live:g}s", flush=True)
                run["live"] = lv = live(long_copy, home, p, a.live)
                if "error" not in lv:
                    print(f"    live: {lv['events'] / a.live:.2f} events/s, {lv['measurements'] / a.live:.2f} readings/s "
                          f"(template {rate['events_per_s']:.2f}, {rate['measurements_per_s']:.2f}); "
                          f"{lv['log_errors']} errors in its log", flush=True)
            run.update({f"after_{k}": v for k, v in store_bytes(p.dir).items() if k != "files"})
            results["demos"][demo]["runs"].append(run)
            (out_dir / "results.json").write_text(json.dumps(results, indent=1, default=str))
            if not a.keep:
                shutil.rmtree(home, ignore_errors=True)
    print(f"results: {out_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
