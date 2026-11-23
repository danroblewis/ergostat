"""The engine's watchdog: the engine found wedged, said, and recovered without anyone restarting it by hand.

Once a second it looks at three things the engine keeps (``engine.py``): when a pass last finished (the loop runs one
at least every ``TICK``), when the loop last went round, and the readings handed to the sensor pool and not given back.

- **The pool wedged**: readings are out and none came back for ``STALL`` seconds, or for the longest of their own
  timeouts and ``GRACE`` more when that is longer (a command is stopped at its timeout, so a pool that gives nothing
  back for longer is held by something else). A fresh pool takes over; the old one's threads are left to finish or not,
  and the readings they held are asked for again.
- **No pass** for ``STALL`` seconds: the loop is started again (the old one stops at its next round, if it ever has
  one).
- **Still no pass** ``STALL`` seconds after that, or a third pool in ``WINDOW``: only a new process recovers it. The
  run loop (``cli/running.py``) restarts it in place, as a change of the model's name does; if that has not happened
  within ``HARD`` seconds, the watchdog restarts the process itself (``engine.restart_hard``). Runs under way are
  stopped by a restart and recorded as stopped with ergostat. The daemons are stopped by it too, their process groups
  sent TERM, then KILL within 3 s (``daemons.supervise.end_all``; on the watchdog's own restart they are never sent
  ``stop`` and their runs are not recorded). Leased items are taken again when their leases end.

Each time it writes every thread's stack to ``<state>/stalls/``, with what holds the item index's lock (the thread in
this process, its stack first, and any other process with the index open), and records ``ergostat.engine.stalled``
(what, for how long, what it did, where the stacks are). A restart that did not help is not repeated at once: the
next waits its turn in ``restarts.py``'s back-off (60 s, 2 m, 4 m, ... 30 m), said once, while the stall lasts.

Every ``BEAT`` seconds it writes ``<state>/heartbeat.json``: when a pass last finished (wall clock) and the pid, for
what watches from outside (``watcher.py``, ``ergostat status``): a process frozen whole leaves it stale. Under
``use: upkeep`` it carries ``stale``, the limit of the goal ``heartbeat-fresh``, which the outer watcher uses (60 to
3600 s). No goal turns this watchdog off: it runs the same whatever the model says."""

from __future__ import annotations

import faulthandler
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from .. import restarts
from .ir import heartbeat_stale, stale_ok

STALL = float(os.environ.get("ERGOSTAT_STALL") or 30.0)   # seconds with no pass, or nothing back from the pool
GRACE = 10.0                # beyond the longest timeout of the readings out
WINDOW = 600.0              # three pools replaced within this long: a restart
HARD = 20.0                 # seconds the run loop is given to restart the process before the watchdog does
EVERY = 1.0
KEPT = 20                   # stack dumps kept
BEAT = 5.0                  # seconds between writes of heartbeat.json
STARTUP = float(os.environ.get("ERGOSTAT_STARTUP") or 120.0)   # seconds a start may take before it is restarted


class Watchdog:
    def __init__(self, eng):
        self.e = eng
        self.thread: threading.Thread | None = None
        self.looped_at: float | None = None       # when it last started the loop again (this stall)
        self.pools: dict[str, list[float]] = {}   # when it replaced each pool (the sensors' "", the alarms' "alarm_")
        self.asked_at: float | None = None        # when it asked for a restart
        self.stalls = 0
        self.beat_at = 0.0
        self.held: tuple[float, str, str] | None = None   # a restart backed off: (when it may be done, why, what)

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="ergostat-watchdog", daemon=True)
        self.thread.start()

    def run(self) -> None:
        while not self.e.stop.wait(EVERY):
            try:
                self.look()
                self.beat()
            except Exception as e:                # the watchdog itself never stops
                self.e.say(f"watchdog: {type(e).__name__}: {e}")

    def beat(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if now - self.beat_at >= BEAT:
            self.beat_at = now
            heartbeat(self.e.p.dir, time.time() - (now - self.e.passed_at), self.stalls,
                      heartbeat_stale(getattr(self.e, "spec", None)),   # (the model as it is now: a reload moves it)
                      getattr(getattr(self.e, "dispatch", None), "failing", None),
                      shard=getattr(self.e, "shard", None), compute=self.compute())

    def compute(self) -> dict | None:
        """The pools' status (SPEC §12s.4) for the heartbeat; None without pools, or when it cannot be read (said:
        the heartbeat is written all the same, and /api/status then shows each pool's status as unknown)."""
        pools = getattr(self.e, "compute", None)
        try:
            return pools.status() if pools is not None else None
        except Exception as e:
            self.e.say(f"watchdog: compute status: {type(e).__name__}")
            return None

    # ---- looking

    def pool_wedged(self, now: float, which: str = "") -> tuple[float, int] | None:
        """(seconds the pool gave nothing back while readings were out, how many are out), when that is too long.
        ``which``: ``alarm_`` for the alarms' own pool."""
        e = self.e
        with e.pool_lock:
            out = list(getattr(e, f"{which}pool_out", {}).values())
            done = getattr(e, f"{which}pool_done_at", 0.0)
        if not out:
            return None
        since = max(done, min(t for t, _, _ in out))
        quiet = now - since
        begun = [timeout for _, timeout, started in out if started is not None]   # (one queued never lengthens it)
        limit = max(STALL, max(begun, default=0.0) + GRACE)
        return (quiet, len(out)) if quiet > limit else None

    def look(self, now: float | None = None) -> None:
        e = self.e
        now = time.monotonic() if now is None else now
        if self.asked_at is not None:             # a restart asked for: the run loop's to do, else ours
            if now - self.asked_at > HARD and e.restart_hard is not None:
                e.say("watchdog: the run loop did not restart the engine; restarting the process")
                self.asked_at = now                   # (tried again after as long, should it not take)
                e.restart_hard(e.wedged)
            return
        if self.held is not None:                  # a restart backed off: done when its turn comes, unless mended
            if now - e.passed_at <= STALL and self.pool_wedged(now) is None and self.pool_wedged(now, "alarm_") is None:
                e.say("watchdog: the engine recovered while a restart waited its turn")
                self.held = None
            elif now >= self.held[0]:
                self.restart(self.held[1], self.held[2], force=True)
            return
        for which in ("", "alarm_"):              # the sensors' pool, and the alarms' own
            wedged = self.pool_wedged(now, which)
            if wedged is not None:
                pools = self.pools.setdefault(which, [])
                pools[:] = [t for t in pools if now - t < WINDOW] + [now]
                if len(pools) >= 3:
                    return self.restart(f"the {'alarms' if which else 'sensor'} pool wedged {len(pools)} times in "
                                        f"{WINDOW / 60:g} min", "pool")
                self.new_pool(*wedged, which)
        quiet = now - e.passed_at
        if quiet <= STALL:
            self.looped_at = None
            return
        if self.looped_at is None:
            self.new_loop(quiet)
        elif now - self.looped_at > STALL:
            self.restart(f"no pass for {quiet:.0f}s, the loop started again {now - self.looped_at:.0f}s ago", "pass")

    # ---- recovering

    def new_pool(self, quiet: float, n: int, which: str = "") -> None:
        e = self.e
        dump = self.dump("pool")
        with e.pool_lock:
            old = getattr(e, f"{which}pool")       # the loop makes a fresh one at its next reading
            setattr(e, f"{which}pool", None)
            held = list(getattr(e, f"{which}pool_out"))
            getattr(e, f"{which}pool_out").clear()
            setattr(e, f"{which}pool_done_at", time.monotonic())
        if old is not None:
            old.shutdown(wait=False, cancel_futures=True)
        if e.lock.acquire(timeout=5):             # (the engine's lock held for good: the pass stall restarts it)
            try:
                for s in held:
                    e.reading.discard(s)
            finally:
                e.lock.release()
        e.wake.set()
        self.said("pool", quiet, f"a new {'alarms' if which else 'sensor'} pool; {n} reading{'s' if n != 1 else ''} "
                  f"asked again", dump)

    def new_loop(self, quiet: float) -> None:
        e = self.e
        dump = self.dump("pass")
        e.loop_gen += 1
        gen = e.loop_gen
        e.full = True
        threading.Thread(target=e._schedule, args=(gen,), name="ergostat-loop", daemon=True).start()
        self.looped_at = time.monotonic()
        e.wake.set()
        self.said("pass", quiet, "the loop started again", dump)

    def restart(self, why: str, what: str, force: bool = False) -> None:
        e = self.e
        left, n = restarts.wait(e.p.dir)
        if left > 0 and not force:                 # the last restart did not help: not again at once
            self.held = (time.monotonic() + left, why, what)
            self.said(what, time.monotonic() - e.passed_at, f"restart {n} backed off {left:.0f}s, the last did not help "
                      f"({why})", self.dump(what))
            return
        self.held = None
        restarts.note(e.p.dir, why, "watchdog")    # (first: the dump may be slow)
        dump = self.dump(what)
        self.asked_at = time.monotonic()
        e.wedged = why
        self.said(what, time.monotonic() - e.passed_at, f"a restart of the process ({why})", dump)

    # ---- saying it

    def dump(self, what: str) -> str | None:
        return dump(self.e.p.dir, what)

    def said(self, what: str, quiet: float, did: str, dump: str | None) -> None:
        """In the log at once; in the record by a thread of its own (a record wedged must not wedge the watchdog)."""
        self.stalls += 1
        e = self.e
        e.say(f"watchdog: the engine stalled ({'nothing back from the sensor pool' if what == 'pool' else 'no pass'} "
              f"for {quiet:.0f}s): {did}" + (f"; every thread's stack in {dump}" if dump else ""))
        from .engine import SOURCE

        def record():
            try:
                e.p.events.add("ergostat.engine.stalled", source=SOURCE,
                               data={"what": what, "seconds": round(quiet, 1), "recovery": did, "stacks": dump,
                                     "pid": os.getpid()})
            except Exception as err:
                e.say(f"watchdog: recording the stall: {type(err).__name__}: {err}")
        threading.Thread(target=record, name="ergostat-watchdog-record", daemon=True).start()


def holders() -> str:
    """What holds each open item index: the thread of this process holding its lock, with its stack, and the other
    processes with its file open (``lsof``), each with its command line."""
    from . import itemindex
    frames, names, out = sys._current_frames(), {t.ident: t.name for t in threading.enumerate()}, []
    try:
        open_ = list(itemindex._OPEN.values())
    except RuntimeError:                           # (changed while read)
        open_ = []
    for ix in open_:
        m = re.search(r"owner=(\d+)", repr(ix.lock))
        owner = int(m.group(1)) if m else 0
        if owner and owner in frames:
            out.append(f"the item index {ix.path.name}: its lock held by thread {names.get(owner, owner)}, at:")
            out += [x.rstrip() for x in traceback.format_stack(frames[owner])]
    files = {os.path.realpath(p): ix.path.name for ix in open_   # (as lsof names them)
             for p in (ix.path, ix.path.with_name(ix.path.name + "-wal")) if p.exists()}
    if files:                                      # one lsof for them all: a dump's time does not grow with the cache
        try:
            got = subprocess.run(["lsof", "-F", "pn", "--", *files], capture_output=True, text=True, timeout=5)
            pid, seen, cmds = 0, set(), {}
            for line in got.stdout.splitlines():
                if line.startswith("p"):
                    pid = int(line[1:])
                elif line.startswith("n") and line[1:] in files and pid and pid != os.getpid():
                    seen.add((files[line[1:]], pid))
            for name, pid in sorted(seen):
                if pid not in cmds:
                    cmds[pid] = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                                               text=True, timeout=5).stdout.strip()[:200]
                out.append(f"the item index {name}: also open in process {pid}: {cmds[pid]}")
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            out.append(f"the item indexes: other processes not looked for ({type(e).__name__})")
    return "\n".join(out) or "no item index held"


def dump(state: Path, what: str) -> str | None:
    """Every thread's stack, and what holds the item index, to ``<state>/stalls/`` (the last ``KEPT`` kept)."""
    d = state / "stalls"
    try:
        d.mkdir(exist_ok=True)
        for old in sorted(d.glob("*.txt"))[:-KEPT + 1]:
            old.unlink(missing_ok=True)
        path = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{what}.txt"
        with open(path, "w") as f:
            f.write(f"ergostat engine stalled ({what}) at {time.strftime('%Y-%m-%d %H:%M:%S')}, pid {os.getpid()}\n\n")
            f.write(holders() + "\n\n")
            f.flush()
            faulthandler.dump_traceback(file=f, all_threads=True)
        return str(path)
    except OSError:
        return None


def startup(state: Path, say, restart, deadline: float | None = None) -> threading.Event:
    """A start not finished (``.set()`` on what is returned) within ``deadline`` seconds: dumped, said, and the process
    restarted (``restart(why)``) when its turn in the back-off comes, unless it finished meanwhile."""
    done = threading.Event()

    def watch():
        if done.wait(STARTUP if deadline is None else deadline):
            return
        where = dump(state, "start")
        left, n = restarts.wait(state)
        why = f"not started within {STARTUP if deadline is None else deadline:.0f}s"
        say(f"watchdog: the engine is {why}" + (f"; every thread's stack in {where}" if where else "")
            + (f"; restart {n} backed off {left:.0f}s, the last did not help" if left else ""))
        if done.wait(left):
            return
        restarts.note(state, why, "startup")
        restart(why)
    threading.Thread(target=watch, name="ergostat-startup", daemon=True).start()
    return done


def heartbeat(state: Path, passed: float, stalls: int = 0, stale: float | None = None,
              failing: tuple[str, float] | None = None, shard: str | None = None, start: bool = False,
              compute: dict | None = None) -> None:
    """``heartbeat.json`` (a shard engine's: ``heartbeat.SHARD.json``, SPEC §9.8): when the last pass finished (wall
    clock), and this pid. Written at start too, so a watcher never reads a slow start by the last process's heartbeat.
    ``stale``: the limit of ``use: upkeep``'s ``heartbeat-fresh`` (``ir.heartbeat_stale``), for the outer watcher; the
    file is written whole each time, so a model without the template leaves no ``stale`` in it. With ``failing``, the
    dispatcher's error while every look meets one, and since when (``dispatch_error``). With ``start`` (the write as
    the run starts, before the model is read): the previous file's ``stale`` when it passes ``stale_ok`` and is at
    least the watcher's 180 s (which comes after ``STARTUP``: a start only ever gets a longer limit), else none."""
    path = state / ("heartbeat.json" if shard is None else f"heartbeat.{shard}.json")
    stale = _last_stale(path) if start and stale is None else stale
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    err = {"dispatch_error": {"why": failing[0], "since": round(failing[1], 3)}} if failing else {}
    err.update({"compute": compute} if compute else {})          # (the pools' status, SPEC §12s.4: with pools only)
    try:
        tmp.write_text(json.dumps({"pass": round(passed, 3), "written": round(time.time(), 3), "stalls": stalls,
                                   "pid": os.getpid(), **({"stale": stale} if stale_ok(stale) else {}), **err}))
        os.replace(tmp, path)
    except OSError:
        pass


def _last_stale(path: Path) -> float | None:
    """The ``stale`` of the heartbeat file at ``path`` when it passes ``stale_ok``; None for anything else (no file,
    one unreadable, not JSON or not an object, a ``stale`` missing, a bool, NaN, out of range, not a number, or under
    the watcher's ``STALE``, so a carried limit never stops a start still inside its own start-up deadline)."""
    from ..watcher import STALE
    try:
        got = json.loads(path.read_text()).get("stale")
    except (OSError, ValueError, AttributeError, RecursionError):
        return None
    return got if stale_ok(got) and got >= STALE else None
