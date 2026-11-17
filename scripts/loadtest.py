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
    files = subprocess.run(["git", "-C", str(demo), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    for f in files:
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
            n_ev += p.events.add_many(batch)
            batch = []
        if len(rows) >= chunk * 4:
            p.measurements.add_many(rows)
            n_me += len(rows)
            rows = []
    if batch:
        n_ev += p.events.add_many(batch)
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("demos", nargs="*", default=["image-squeeze", "the-job"])
    ap.add_argument("--days", default="1,7,30", help="how long each long record is, comma separated")
    ap.add_argument("--capture", type=float, default=120, help="seconds each demo runs for its template")
    ap.add_argument("--live", type=float, default=60, help="seconds the demo runs on the long record (0: not at all)")
    ap.add_argument("--windows", default="1h,1d,30d", help="the page windows asked for")
    ap.add_argument("--timeout", type=float, default=60, help="a client's patience, seconds")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep", action="store_true", help="keep the long records")
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
            p = project(copy, home)
            print(f"  {days:g} days: writing", flush=True)
            made = synthesize(p, evs, series, t0, t1, days, time.time())
            run = {"days": days, **made, **store_bytes(p.dir)}
            print(f"    {made['events']} events, {made['measurements']} readings in {made['write_seconds']:.0f}s; "
                  f"events {run['events_bytes'] / 1e6:.1f} MB, measurements {run['measurements_bytes'] / 1e6:.1f} MB", flush=True)
            run["server"] = serve_and_ask(copy, home, p, a.windows.split(","), a.timeout)
            if a.live:
                print(f"    running the demo on it for {a.live:g}s", flush=True)
                run["live"] = lv = live(copy, home, p, a.live)
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
