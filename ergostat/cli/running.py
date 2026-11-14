"""``ergostat run``, ``ergostat web`` and ``ergostat chat``."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from .. import model as mdl
from ..show import c, table
from .common import open_project, out_json


def cmd_run(args) -> int:
    from .. import runner
    p = open_project(args)
    pid = runner.running_pid(p)
    if args.stop:
        if not pid:
            print("not running")
            return 0
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not runner.running_pid(p):
                print(f"stopped ({pid})")
                return 0
            time.sleep(0.1)
        print(f"{pid} did not stop within 10s; it still holds {runner.pid_file(p)}", file=sys.stderr)
        return 1
    errors = [msg for lv, msg in mdl.check(p.model) if lv == "error"]
    if errors:
        print("the model has errors; fix them first (ergostat check):", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 2
    if not args.foreground:
        if pid:
            print(f"already running ({pid})" + (f" · {runner.web_url(p)}" if runner.web_url(p) else ""))
            return 0
        extra = [*(["--no-web"] if args.no_web else []), *(["--port", str(args.port)] if args.port else [])]
        child = runner.start_background(p, extra)
        for _ in range(100):
            if runner.running_pid(p) == child and (args.no_web or runner.web_url(p)):
                break
            time.sleep(0.1)
        print(f"running ({child}) · log {p.dir / 'run.log'}" + (f"\nweb: {runner.web_url(p)}" if runner.web_url(p) else ""))
        print(c("see it: ergostat · stop it: ergostat run --stop", "dim"))
        return 0
    if not runner.take_lock(p):
        print(f"already running ({runner.running_pid(p)}): one runner per repository", file=sys.stderr)
        return 1
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
    server = None
    if not args.no_web:                                 # the page first, so its address is known at once
        from ..store import Project
        from ..web import serve
        server, url = serve(Project(mdl.load(p.repo), p.dir), args.port)   # its own model: the page never hands the runner one
        print(f"web: {url}", flush=True)
    r = runner.Runner(p, say=lambda s: print(time.strftime("%H:%M:%S"), s, flush=True))
    r.start()
    print(f"running {len(r.queues)} agents", flush=True)
    mtime = p.model.path.stat().st_mtime if p.model.path else 0
    reload = False
    try:
        while not stopping:
            time.sleep(0.5)
            try:
                now_m = p.model.path.stat().st_mtime if p.model.path else 0
            except OSError:
                continue
            if now_m != mtime:
                mtime = now_m
                try:
                    fresh = mdl.load(p.model.path.parent)
                except Exception as e:
                    print(f"{mdl.FILE} changed but does not load ({e}); still running the last one", flush=True)
                    continue
                if any(lv == "error" for lv, _ in mdl.check(fresh)):
                    print(f"{mdl.FILE} changed but has errors (ergostat check); still running the last one", flush=True)
                    continue
                print(f"{mdl.FILE} changed: restarting with it", flush=True)
                reload = True
                break
    except KeyboardInterrupt:
        pass
    r.close()
    if server:
        server.shutdown()
        server.server_close()
        (p.dir / "web.json").unlink(missing_ok=True)
    if reload and not stopping:                         # the same process, the new model (a stop asked meanwhile wins)
        os.environ.update(runner.keep_lock_across_exec())
        os.execv(sys.executable, [sys.executable, "-m", "ergostat", "-C", str(p.repo), "run", "--foreground",
                                  *(["--no-web"] if args.no_web else []), *(["--port", str(args.port)] if args.port else [])])
    return 0

def cmd_snapshot(args) -> int:
    from ..web.snapshot import build
    p = open_project(args)
    since = getattr(args, "since", None) or "1h"
    if getattr(args, "at", None):
        print("a snapshot is of now: --at is not taken", file=sys.stderr)
        return 2
    out = Path(args.output or f"{p.model.name}-{time.strftime('%Y%m%d-%H%M')}.html")
    html = build(p, since)
    out.write_text(html)
    print(f"{out}  ({len(html) // 1024} KB; open it in a browser, no ergostat needed)")
    return 0


def cmd_web(args) -> int:
    from ..web import serve
    p = open_project(args)
    server, url = serve(p, args.port)
    print(f"web: {url}  (Ctrl-C stops it)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
        (p.dir / "web.json").unlink(missing_ok=True)
    return 0

def cmd_chat(args) -> int:
    from .. import supervisor
    here = Path(args.C).resolve() if args.C else Path.cwd()
    return supervisor.chat(here, " ".join(args.message) or None, print_only=args.print_prompt)


def cmd_projects(args) -> int:
    """``ergostat projects``: every project on this machine ergostat has seen."""
    from ..projects import known
    found = known()
    if args.json:
        return out_json(found)
    rows = []
    for x in found:
        if x.get("error"):
            rows.append([x["name"], c("cannot load", "bad"), "", "", x["error"][:60]])
            continue
        state = c("running", "ok") if x["running"] else c("stopped", "dim")
        names = ", ".join(x["off"][:3]) + (f" +{len(x['off']) - 3}" if len(x["off"]) > 3 else "")
        unknown = f", {len(x.get('unknown', []))} unknown" if x.get("unknown") else ""
        held = x["loops"] - len(x["off"]) - len(x.get("unknown", []))
        off = (c(f"{len(x['off'])} off: {names}", "bad") + unknown if x["off"] else
               (c(f"{held} holding", "ok") if held else "") + (unknown.lstrip(", ") if not held else unknown) if x["loops"] else "no loops")
        rows.append([x["name"], state, off, x["web"] or "", x["repo"]])
    print(table(["PROJECT", "STATE", "LOOPS", "PAGE", "REPOSITORY"], rows, "no projects yet: ergostat run in a repository"))
    return 0
