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
  stopped by a restart and recorded as stopped with ergostat; leased items are taken again when their leases end.

Each time it writes every thread's stack to ``<state>/stalls/`` and records ``ergostat.engine.stalled`` (what, for how
long, what it did, where the stacks are)."""

from __future__ import annotations

import faulthandler
import os
import threading
import time

STALL = float(os.environ.get("ERGOSTAT_STALL") or 30.0)   # seconds with no pass, or nothing back from the pool
GRACE = 10.0                # beyond the longest timeout of the readings out
WINDOW = 600.0              # three pools replaced within this long: a restart
HARD = 20.0                 # seconds the run loop is given to restart the process before the watchdog does
EVERY = 1.0
KEPT = 20                   # stack dumps kept


class Watchdog:
    def __init__(self, eng):
        self.e = eng
        self.thread: threading.Thread | None = None
        self.looped_at: float | None = None       # when it last started the loop again (this stall)
        self.pools: list[float] = []              # when it replaced the pool
        self.asked_at: float | None = None        # when it asked for a restart
        self.stalls = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="ergostat-watchdog", daemon=True)
        self.thread.start()

    def run(self) -> None:
        while not self.e.stop.wait(EVERY):
            try:
                self.look()
            except Exception as e:                # the watchdog itself never stops
                self.e.say(f"watchdog: {type(e).__name__}: {e}")

    # ---- looking

    def pool_wedged(self, now: float) -> tuple[float, int] | None:
        """(seconds the pool gave nothing back while readings were out, how many are out), when that is too long."""
        e = self.e
        with e.pool_lock:
            out = list(e.pool_out.values())
            done = e.pool_done_at
        if not out:
            return None
        since = max(done, min(t for t, _ in out))
        quiet = now - since
        limit = max(STALL, max(timeout for _, timeout in out) + GRACE)
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
        wedged = self.pool_wedged(now)
        if wedged is not None:
            self.pools = [t for t in self.pools if now - t < WINDOW] + [now]
            if len(self.pools) >= 3:
                return self.restart(f"the sensor pool wedged {len(self.pools)} times in {WINDOW / 60:g} min", "pool")
            self.new_pool(*wedged)
        quiet = now - e.passed_at
        if quiet <= STALL:
            self.looped_at = None
            return
        if self.looped_at is None:
            self.new_loop(quiet)
        elif now - self.looped_at > STALL:
            self.restart(f"no pass for {quiet:.0f}s, the loop started again {now - self.looped_at:.0f}s ago", "pass")

    # ---- recovering

    def new_pool(self, quiet: float, n: int) -> None:
        e = self.e
        dump = self.dump("pool")
        with e.pool_lock:
            old, e.pool = e.pool, None             # the loop makes a fresh one at its next reading
            held = list(e.pool_out)
            e.pool_out.clear()
            e.pool_done_at = time.monotonic()
        if old is not None:
            old.shutdown(wait=False, cancel_futures=True)
        if e.lock.acquire(timeout=5):             # (the engine's lock held for good: the pass stall restarts it)
            try:
                for s in held:
                    e.reading.discard(s)
            finally:
                e.lock.release()
        e.wake.set()
        self.said("pool", quiet, f"a new sensor pool; {n} reading{'s' if n != 1 else ''} asked again", dump)

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

    def restart(self, why: str, what: str) -> None:
        e = self.e
        dump = self.dump(what)
        self.asked_at = time.monotonic()
        e.wedged = why
        self.said(what, time.monotonic() - e.passed_at, f"a restart of the process ({why})", dump)

    # ---- saying it

    def dump(self, what: str) -> str | None:
        d = self.e.p.dir / "stalls"
        try:
            d.mkdir(exist_ok=True)
            for old in sorted(d.glob("*.txt"))[:-KEPT + 1]:
                old.unlink(missing_ok=True)
            path = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{what}.txt"
            with open(path, "w") as f:
                f.write(f"ergostat engine stalled ({what}) at {time.strftime('%Y-%m-%d %H:%M:%S')}, pid {os.getpid()}\n\n")
                f.flush()
                faulthandler.dump_traceback(file=f, all_threads=True)
            return str(path)
        except OSError:
            return None

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
