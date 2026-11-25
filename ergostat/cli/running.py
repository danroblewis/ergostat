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


def _wait_for_a_model_that_runs(args) -> None:
    """A runner restarted in place (a new name or store, or a watchdog's last resort) whose files were edited again
    meanwhile waits, holding its lock, until they settle into a model that may run, rather than exiting."""
    from .. import reload as rl
    here = Path(args.C).resolve() if args.C else Path.cwd()
    said, good = None, None
    while True:
        try:
            m = mdl.load(here)
            errors = [msg for lv, msg in mdl.check(m, warnings=False) if lv == "error"]
        except FileNotFoundError:
            return                                       # (open_project says so)
        except Exception as e:
            lines = [x.strip() for x in str(e).splitlines()[1:] if x.strip()]
            errors = lines or [f"{type(e).__name__}: {e}"]
        if not errors:
            stamp = mdl.stamp(m)
            if good == stamp:
                return
            good = stamp
            time.sleep(rl.SETTLE)
            continue
        good = None
        if errors != said:
            print(f"restarting: {rl.banner(errors).replace('; still running the last good version', '')}; waiting for it "
                  f"to be fixed:", flush=True)
            for msg in errors:
                print(f"  {msg}", flush=True)
            said = errors
        time.sleep(0.5)


def _stop(p, pid) -> int:
    from .. import runner
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


def _stop_runs(p, rc: int) -> int:
    """``--stop --runs``: the runs left going by their keepers (``runs: outlive_engine``, SPEC §9.1) stopped too, each
    whole process group (SIGTERM, SIGKILL past the grace), engine or none; waited for, a grace and 5 s at most. So are
    the daemons kept going by theirs (SPEC §9.7), each in ``daemons/KEY/runs``."""
    from ..compute.worker import keeper
    from ..leases.kill import grace
    root, g = str(p.dir.resolve()), grace()
    roots = [root] + sorted(str(d) for d in (p.dir.resolve() / "daemons").glob("*") if d.is_dir())
    asked = [os.path.join(r, "runs", n) for r in roots for n in keeper.stop_all(r, g)]
    end = time.monotonic() + g + 5
    left = asked
    while left and time.monotonic() < end:
        time.sleep(0.1)
        left = [r for r in left if keeper.ended(r) is None]
    if asked:
        print(f"stopped {len(asked) - len(left)} of {len(asked)} runs left going")
    if left:
        print(f"still going: {', '.join(os.path.basename(r)[:8] for r in left)}", file=sys.stderr)
        return 1
    return rc


def _metrics_answer(p) -> bool:
    """Whether the VictoriaMetrics that keeps the readings answers; when it does not, said, with how to start one (the
    readings are kept nowhere else: never a run that loses them)."""
    from ..victoria import VictoriaError
    try:
        p.measurements.check()
    except VictoriaError as e:
        print(f"ergostat run: {e}", file=sys.stderr)
        return False
    return True


def cmd_run(args) -> int:
    from .. import runner
    if args.foreground and os.environ.get("ERGOSTAT_LOCK_FD") and not args.stop:
        _wait_for_a_model_that_runs(args)
    p = _stand_in(args) if args.stop or (args.service and args.uninstall) else open_project(args)
    pid = runner.running_pid(p)
    if args.stop:
        from ..watcher import STOPPED
        (p.dir / STOPPED).touch()                       # on purpose: the outer watcher leaves it stopped
        rc = _stop(p, pid)
        return _stop_runs(p, rc) if getattr(args, "runs", False) else rc
    if (args.install or args.uninstall) and not args.service:
        print("--install and --uninstall go with --service: ergostat run --service --install", file=sys.stderr)
        return 2
    if getattr(args, "service", None):
        return _service(p, args)
    errors = [msg for lv, msg in mdl.check(p.model, warnings=False) if lv == "error"]
    if errors:
        print("the model has errors; fix them first (ergostat check):", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 2
    if not p.storage.run and not _metrics_answer(p):    # (with run:, the engine starts it: the daemon victoriametrics)
        return 1
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
        # not a failure: what was asked for (a runner here) is so; a service manager must not retry it
        print(f"already running ({runner.running_pid(p)}): one runner per repository", file=sys.stderr)
        return 0
    from ..watcher import STOPPED
    (p.dir / STOPPED).unlink(missing_ok=True)           # started: a stop on purpose is over
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
    from ..spec.watchdog import heartbeat, startup
    heartbeat(p.dir, time.time(), start=True)         # this process's, before its slow start (the last stale kept)
    eng: list = []                                      # the engine, once made: its dispatch closed by a hard restart
    hard = lambda why: _restart_hard(p, args, why, *eng)                  # noqa: E731
    started = startup(p.dir, lambda s: print(time.strftime("%H:%M:%S"), s, flush=True),
                      hard)                             # a start that hangs (a lock held elsewhere): restarted
    from ..storage import rotate, trim
    rotate(p.dir / "run.log", p.storage.logs["run"])    # (storage: logs:) on every start, in the background or not
    trim(p.dir / "threads.txt", p.storage.logs["threads"])
    import faulthandler
    stacks = open(p.dir / "threads.txt", "a")           # noqa: SIM115  (kill -USR1 PID: every thread's stack, here)
    faulthandler.register(signal.SIGUSR1, file=stacks, all_threads=True)
    from .. import reload as rl
    watch = rl.Settled(p.model)     # a change taken once the files settle, and only if it may run: followed from before
    server = None                   # any run starts, so an edit made while it starts is not taken as the files it ran from
    if not args.no_web:                                 # the page first, so its address is known at once
        from ..store import Project
        from ..web import serve
        server, url = serve(Project(p.model, p.dir), args.port)   # its own Project: the page never hands the runner a model
        print(f"web: {url}", flush=True)
        print(f"push: POST {url}/api/events (token: {p.dir / 'intake.token'})", flush=True)
        if server.mtls_said:                            # web: mtls: where it listens, or why it does not
            print(server.mtls_said, flush=True)
    say = lambda s: print(time.strftime("%H:%M:%S"), s, flush=True)       # noqa: E731
    if getattr(p.model, "spec", None) is not None:      # the YAML model: ergostat closes its loops itself
        from ..spec.engine import Engine
        r = Engine(p, say=say)
        eng.append(r)
        r.restart_hard = hard
        r.start_all()
        sp = p.model.spec
        print(f"running {len(sp.sensors())} sensors, {len(r.builtins)} built-in blocks, {len(r.machines)} machine blocks",
              flush=True)
    else:
        r = runner.Runner(p, say=say)
        r.start()
        print(f"running {len(r.queues)} agents", flush=True)
    from ..remote import refresh as remote_refresh
    remote_refresh.start(lambda: p)                     # remotes' models kept current: a new version reloads (SPEC §4c)
    started.set()
    from ..goodmodel import keep

    def _kept() -> None:                                # for the command line while the files have errors (SPEC §9.1)
        why = keep(p)
        if why:
            print(f"the last good model could not be kept ({why})", flush=True)
    _kept()
    rl.write_state(p.dir, None)
    name = mdl.file_name(p.model)
    reload = moved = False
    try:
        while not stopping:
            time.sleep(0.25)
            wedged = getattr(r, "wedged", None)         # the engine's watchdog could not recover it in place
            if wedged:
                print(f"the engine is wedged ({wedged}): restarting it (its runs are stopped)", flush=True)
                reload = True
                break
            due = watch.due()
            if due is None:
                continue
            began = time.monotonic()
            fresh, errors = rl.load_checked(p.model)
            loaded = time.monotonic() - began
            if fresh is None:                           # each one, so the log alone is enough to fix it
                watch.refused(due)
                rl.write_state(p.dir, errors, getattr(r, "version", None))
                print(f"{name} changed: {rl.banner(errors)}:", flush=True)
                for msg in errors:
                    print(f"  {msg}", flush=True)
                continue
            if fresh.name != p.model.name or (getattr(fresh, "spec", None) is None) != (getattr(p.model, "spec", None) is None) or \
                    getattr(fresh, "storage", None) != getattr(p.model, "storage", None):
                # another state directory, format or store: not the same runner any more
                print(f"{name} changed its name, format or storage: restarting with it (its runs are stopped)", flush=True)
                rl.write_state(p.dir, None)
                reload, moved = True, fresh.name != p.model.name           # (a new name: a new state folder)
                break
            old = p.model
            try:                                        # in place: runs under way carry on (SPEC §9.1)
                got = r.swap(fresh)
            except Exception as e:                      # nothing of it was taken: the last one runs as it was
                watch.refused(due)
                why = f"{name}: it could not be taken in place ({type(e).__name__}: {e})"
                rl.write_state(p.dir, [why], getattr(r, "version", None))
                print(f"{why}; still running the last good version", flush=True)
                continue
            watch.took(fresh, due)
            _kept()
            rl.write_state(p.dir, None)
            name = mdl.file_name(p.model)
            took = time.monotonic() - began
            n = got["carried"]
            secs = got.get("seconds") or {}
            print(f"{name} changed: version {got['version']} from now ({took:.2f}s)"
                  + (f"; {n} run{'s' if n != 1 else ''} under way carr{'y' if n != 1 else 'ies'} on under the last one "
                     f"({', '.join(got['runs'])})" if n else ""), flush=True)
            if took > rl.SLOW:                          # where the time went
                parts = {"reading and checking the files": loaded, "taking it in place": secs.get("swap", 0.0),
                         "recording the change": secs.get("record", 0.0)}
                slow = max(parts, key=parts.get)
                print(f"  slow change ({took:.1f}s), most of it {slow} ({parts[slow]:.1f}s): "
                      + ", ".join(f"{k} {v:.2f}s" for k, v in parts.items())
                      + f"; {len(getattr(old, 'files', None) or [])} files", flush=True)
    except KeyboardInterrupt:
        pass
    if reload and getattr(r, "wedged", None) and not stopping:
        hard(r.wedged)                                  # (closing may wait on what is wedged)
    if kept := reload and not stopping and not moved and getattr(r, "calls", None):
        kept.keep = True                                # its socket left: a run's calls wait for the new engine's
    r.close()
    if server:
        server.shutdown()
        server.server_close()
        (p.dir / "web.json").unlink(missing_ok=True)
    if reload and not stopping:                         # the same process, the new model (a stop asked meanwhile wins)
        _restart(p, args)
    if kept:                                            # not started again after all: its calls fall back after GONE
        kept.remove()
    return 0


def _stand_in(args):
    """For ``--stop`` and ``--service --uninstall``, which need only the state folder and the repository: with the files
    broken, the folder found without the model."""
    from types import SimpleNamespace

    from ..projects import state_of
    from ..store import Project
    main = mdl.find(Path(args.C).resolve() if args.C else Path.cwd())
    if main is not None:
        try:
            return Project(mdl.load(main.parent))
        except Exception:
            if (d := state_of(main)) is not None:
                return SimpleNamespace(dir=d, repo=main.parent, model=None)
    return open_project(args)                           # (which says what is wrong)


def _service(p, args) -> int:
    """``run --service``: the unit printed (the default), installed (``--install``) or removed (``--uninstall``)."""
    from .. import runner, service
    port = args.port
    if not port and not args.no_web and runner.web_url(p):           # keep the page where it is now
        port = int(runner.web_url(p).rsplit(":", 1)[1])
    py = service.python()
    if py is None and not args.uninstall:
        print("no installed ergostat on PATH to run as a service (this one runs from a repository's .venv or a "
              "temporary environment); install it first: uv tool install ergostat (or pipx), then ergostat run --service",
              file=sys.stderr)
        return 2
    body, path, load, unload = service.text(p, [*(["--no-web"] if args.no_web else []),
                                                *(["--port", str(port)] if port else [])], args.service, py or "")
    if not (args.install or args.uninstall):
        print(body, end="")
        print(c(f"save it as {path}, then: {' && '.join(' '.join(x) for x in load)} (or: ergostat run --service "
                f"--install)", "dim"), file=sys.stderr)
        return 0
    if path.exists():
        service.run(unload)                             # (installed before: replaced)
    if args.uninstall:
        path.unlink(missing_ok=True)
        print(f"removed {path}; ergostat runs here only when started (ergostat run)")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    wrong = service.run(load)
    print(f"installed {path}: it keeps ergostat running here, restarted when it dies or freezes, and at login "
          f"(ergostat run --service --uninstall removes it)")
    for w in wrong:
        print(f"  could not load it: {w}", file=sys.stderr)
    return 1 if wrong else 0


def _restart(p, args) -> None:
    """This runner, started again in its own process (its lock kept across): a new model's name or store, or the
    watchdog's last resort. Every daemon's process group ended first (``supervise.end_all``: TERM, KILL within 3 s),
    those a closed supervisor no longer saw too (a warm process dying, a group whose KILL a thread had yet to send)."""
    from .. import runner
    from ..daemons import proc, supervise
    from ..leases.kill import grace
    os.environ.update(runner.keep_lock_across_exec())
    if n := len(supervise.end_all(min(grace(), 3.0))):
        print(f"ended {n} daemon process group{'s' if n != 1 else ''} before starting again", flush=True)
    try:
        os.execv(sys.executable, [sys.executable, "-m", "ergostat", "-C", str(p.repo), "run", "--foreground",
                                  *(["--no-web"] if args.no_web else []), *(["--port", str(args.port)] if args.port else [])])
    except OSError:                                     # (not started again: daemons may be spawned once more)
        with proc.GROUPS_LOCK:
            proc.CLOSING = False
        raise


def _restart_hard(p, args, why, eng=None) -> None:
    """The watchdog's restart when the run loop could not do it: the engine's dispatch closed first (its stop set,
    waiting at most 1 s for its lock), so no lease is taken while the daemons' groups end and a run spawned from now
    kills itself; its runs killed, its daemons' groups ended (by ``_restart``: TERM, KILL within 3 s, never ``stop``
    nor drained), nothing else waited on (what is wedged may be what closing would wait for: no supervisor's lock, no
    event recorded)."""
    from .. import runner
    print(f"restarting the engine's process at once ({why})", flush=True)
    if eng is not None:
        eng.shut(min(eng.lock_wait, 1.0))
    runner.kill_all()
    _restart(p, args)

def cmd_snapshot(args) -> int:
    from ..web.snapshot import build
    p = open_project(args)
    since = getattr(args, "since", None) or "1h"
    from ..durations import parse_duration
    parse_duration(since, "--since")                     # a bad window is refused here, as everywhere
    if getattr(args, "at", None):
        print("a snapshot is of now: --at is not taken", file=sys.stderr)
        return 2
    out = Path(args.output or f"{p.model.name}-{time.strftime('%Y%m%d-%H%M')}.html")
    html = build(p, since, logs=args.with_logs)
    out.write_text(html)
    print(f"{out}  ({len(html) // 1024} KB; open it in a browser, no ergostat needed)")
    return 0


def cmd_web(args) -> int:
    from ..web import serve
    p = open_project(args)
    server, url = serve(p, args.port)
    from ..remote import refresh as remote_refresh
    remote_refresh.start(server.RequestHandlerClass.live.get)    # remotes' models kept current (SPEC §4c)
    print(f"web: {url}  (Ctrl-C stops it)", flush=True)
    if server.mtls_said:
        print(server.mtls_said, flush=True)
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
    from .. import state as st
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
        g, sys_off = x["goals"], x["goals_off"]           # the one count (state.goals_off), as `ergostat` says it
        names = ", ".join(sys_off[:3]) + (f" +{len(sys_off) - 3}" if len(sys_off) > 3 else "")
        off = c(st.goals_said(g) + (f": {names}" if names else ""), "bad" if g["system"] else "ok") if x["loops"] else "no goals"
        rows.append([x["name"], state, off, x["web"] or "", x["repo"]])
    print(table(["PROJECT", "STATE", "GOALS", "PAGE", "REPOSITORY"], rows, "no projects yet: ergostat run in a repository"))
    return 0
