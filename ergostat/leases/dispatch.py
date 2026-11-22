"""The engine's dispatcher and watchdog for blocks that take items (SPEC §9.5).

- **Dispatch.** For each block that takes items: while nothing commands it, or what commands it is on, every item of
  its kind in one of its ``at`` states, not held, not put off (``not_before``), and matching its ``where``, is leased
  to a run of its own, oldest first, while the block's runs in flight (its leases held, from the fold, and the runs
  going here) are fewer than its pool now (``poolnow.py``: its ``pool:``, or its stock's level as the engine last read
  it, at most its ``most``, read in the same hold of the lock as the count and the take). An item put off
  (``not_before``) is looked at again when it falls due. It looks whenever the record has something new (an item reaching its
  state starts a run at once; the lease is caused by that event), woken by the write itself (``notify.py``; another
  process's write by the kernel's file notification, else at its next check, every quarter second), and every second
  besides.
- **The run.** Given its item (its folded fields) and its lease in its input; ``ERGOSTAT_ITEM`` and ``ERGOSTAT_LEASE``
  (the fencing number; the holder is ``ERGOSTAT_RUN``) in its environment; its event lines are about its item by
  default. When it ends, its lease ends: ack when the work moved the item on (to a state of ``to``, or any but where
  it was taken from), nack otherwise (or when it said ``{"nack": ...}``), the why its exit or its own words.
- **The watchdog.** A held lease past its expiry is looked at once more: a line of the item's transcript, an event the
  holder caused about anything, or about an item the holder started (its session), since it was last renewed, renews
  it (``ergostat.lease.renewed``, at that time); otherwise it expires (``ergostat.lease.expired``), and its run, when
  this engine started it, is killed (``kill.py``); what a run says about the item after its lease ended is refused.
  It expires only on a second look at the same expiry, ``grace(ttl)`` after the pass that first found it overdue
  (renewed since, late, and overdue again: a first look again): a renewal the run
  asked for in time may still be on its way into the record (the engine busy, its socket's caller waiting for a
  thread), and a pass that comes late (a loaded machine, one that slept) must not judge on what it has not yet read.
  Just before it writes the expiry, it reads the lease again from the record, and writes nothing when it was renewed
  past the expiry it judged. The expiry names the ``expires`` it judged, so a renewal recorded in the moment between
  that read and the write still wins (the fold refuses it); what reads expiries raw leaves those out
  (``fold.refused_expiries``)."""

from __future__ import annotations

import threading
import time
import uuid

from ..spec import items as its
from ..spec.ir import DEAD, LEASED, own_kind
from . import ENDED, EXPIRED, RENEWED, TAKEN, poolnow
from .fold import held
from .kill import kill
from .ready import Ready, ordered, unblocked
from .terms import grace, terms

SOURCE = "ergostat"
LOOK = 0.25           # seconds between looks at the record for something new, when no write wakes it (notify.py)
EVERY = 1.0           # a look at every block's queue, and the watchdog's pass, at least this often
GAP = 0.005           # seconds a look waits after a write wakes it, for the writes that come with it


def moved_on(b, it) -> bool:
    """Whether the work moved the item on: to a state of the block's ``to`` (when it has one), or to any state but
    where it was taken from and ``leased``."""
    if it.state in (LEASED, DEAD, *b.takes.at):
        return False
    return not b.takes.to or it.state in b.takes.to


def terminal(spec, kind: str | None, state: str | None) -> bool:
    """Whether an item in this state is finished: a dead letter, or in its kind's last state (``dead`` aside)."""
    if state == DEAD:
        return True
    k = spec.items.get(kind or "")
    rest = [x for x in (k.states if k else []) if x != DEAD]
    return bool(rest) and state == rest[-1]


class Dispatcher:
    def __init__(self, eng):
        self.e, self.p = eng, eng.p
        self.going: dict[str, dict[str, dict]] = {}   # block → item → {run, fence, block}: the runs going here
        self.ours: set[str] = set()                   # the runs this engine took whose leases have not ended
        self.holding = False                          # whether the last watch found a lease held (one outlives its block)
        self.lock = threading.RLock()
        self.ends = threading.Lock()                  # finish's read and its write of lease.ended, as one
        self.seq = 0
        self.kept = Ready()                           # the items a look needs, followed as events arrive (ready.py)
        self.stale = True                             # read the record again before the next use: once a look, and after a take
        self.due = float("inf")                       # when the first item put off (not_before) may be taken
        self.due_now: set[str] = set()                # items put off that may be taken now (their daemon revived)
        self.overdue: dict[tuple, float] = {}         # (item, fence, expires) → when (monotonic) a pass first found it overdue
        self.mine: dict[str, tuple] = {}              # run → (block, item, fence): the leases taken here, not yet ended
        self.unread: set[str] = set()                 # blocks whose pool's stock has no reading, said once
        self.hold: str | None = None                  # why the last trip check could not read its inputs: pool 0 till one can

    @property
    def spec(self):
        """The model as it is now: a lease taken under an earlier one is still held, renewed and fenced as it was."""
        return self.e.spec

    @property
    def blocks(self) -> list:
        spec = self.spec
        return [b for b in spec.blocks.values() if b.takes and b.machine and self.e.own(f"block.{b.name}", spec)]

    def kinds(self) -> list[str]:
        """The kinds whose leases are watched: every kind of the model's own (a lease outlives the block that took it),
        of the engine's shard (SPEC §9.8: a kind is in the shard of the blocks that take it, else of its system)."""
        spec = self.spec
        return [k for k in spec.items if own_kind(k) and self.e.own(f"kind.{k}", spec)]

    # ---- the clock

    def run(self) -> None:
        from ..notify import of
        board = of(self.p.events)
        mark = board.n if board else 0
        last = 0.0
        while not self.e.stop.is_set():
            try:
                seq = self.p.events.last_seq()
                mono = time.monotonic()
                if seq != self.seq or mono - last >= EVERY or time.time() >= self.due:
                    self.seq = seq
                    self.due = float("inf")
                    if mono - last >= EVERY:
                        last = mono
                        if self.spec.operating:              # the trips, once a second (SPEC §9.5, operating states)
                            self.trip()
                        if self.blocks or self.holding:     # (a model with no block that takes: nothing to watch)
                            self.watch()
                    self.tick()
            except Exception as e:                             # the next look tries again
                self.e.say(f"leases: {type(e).__name__}: {e}")
            wait = max(0.0, min(LOOK, self.due - time.time()))      # (an item put off is due before the next look)
            if board is None:
                self.e.stop.wait(wait)
                continue
            was, mark = mark, board.wait(mark, wait)
            if mark != was:
                self.e.stop.wait(GAP)

    # ---- operating states (SPEC §9.5)

    def trip(self, now: float | None = None) -> None:
        """The trips looked at, under the lock across their read, decision and write. Inputs that cannot be read hold
        dispatch at pool 0 until a look reads them cleanly."""
        from ..operating import trips
        with self.lock:
            try:
                self.hold = trips.check(self.p, self.spec, now, say=self.e.say)
            except Exception as e:                             # a write that raised holds too (worst case, lesson-3)
                self.hold = f"the trips could not be checked: {type(e).__name__}: {e}"
        if self.hold:
            self.e.say(f"operating: {self.hold}")

    def cap(self) -> tuple[int | None, str]:
        """The pool the operating state in force allows each block that takes items (None: no cap), and why. A model
        that declares no state reads nothing."""
        if not self.spec.operating:
            return None, ""
        if self.hold:
            return 0, self.hold
        from ..operating.fold import in_force
        _, pool, why = in_force(self.p, self.spec)
        return pool, why

    def flying(self, b, but: str) -> int:
        """The block's runs in flight, from the fold and here, besides the item ``but``."""
        self.stale = True
        every, _ = self.items_of(b.takes.kind)
        mine = {i.id for i in every if (held(i.fields) or {}).get("block") == b.name}
        return len((mine | set(self.going.get(b.name, {}))) - {but})

    def entered_meanwhile(self, b, it, lease: dict, run: str, fence: int, inline: bool) -> bool:
        """Read again just after the lease was written (everything recorded before it is seen): when the cap leaves
        no room for this run now, counting those in flight, the lease ends at once, uncounted, and no run starts. A
        run by hand (``inline``) ignores the block's pool, so only pool 0 gives it back."""
        pool, why = self.cap()
        if pool is None or (pool > 0 and (inline or self.flying(b, it.id) < pool)):
            return False
        self.p.events.add(ENDED, item=it.id, source=SOURCE, causedby=run,
                          data={"run": run, "fence": fence, "how": "nack", "why": why, "count": False,
                                **self.after(it, lease, False)})
        self.e.say(f"{b.name}: gave {it.id} back at once: {why}")
        return True

    # ---- dispatch

    def items_of(self, kind: str) -> tuple[list, object]:
        """A kind's items a look needs, the latest first: those in a state a block takes from, and those held (every
        item of the kind, read whole, when the record has no item index); and the index they were read from."""
        ix = self.kept.ix if not self.stale else self.kept.follow(self.p.events, self.spec, self.kinds, lambda: self.blocks)
        if ix is None:
            return its.project(self.p.events, self.spec, kind, transcript=False), None
        self.stale = False
        return self.kept.of(kind), ix

    @staticmethod
    def whole(ix, it):
        """An item as ``items.project`` reads it, its moves with it (a look reads them only of the items it takes)."""
        if ix is None:
            return it
        with ix.lock:
            got = ix.items(it.kind, ids=[it.id])
        return got[0] if got else it

    def handing(self, daemon: str) -> int:
        """Runs taken for this daemon's blocks and not yet held by it (their threads starting)."""
        return sum(1 for x in self.blocks if x.params.get("daemon") == daemon
                   for g in self.going.get(x.name, {}).values() if not self.e.daemons._held(g["run"]))

    def going_items(self) -> set[str]:
        return {i for g in self.going.values() for i in g}

    def tick(self) -> None:
        """Lease what each block may take now, and start a run for each. The record is read once a look, and again after
        each lease it takes (each block sees what the blocks before it took): not once for every block, which kept the
        look waiting on the item index behind every reading's count (docs/proposals/scale.md)."""
        now = time.time()
        self.stale = True
        cap = self.cap()[0] if self.blocks else None       # (read once a look: a state never raises a block's pool)
        for b in self.blocks:
            if self.e.stop.is_set() or b.name in self.e.held:
                return
            cmd, _ = self.e.command_of(b)
            if cmd is not None and not cmd:                    # commanded, and nothing commands it now: it takes nothing
                continue
            with self.lock:
                every, ix = self.items_of(b.takes.kind)
                mine = {i.id for i in every if (held(i.fields) or {}).get("block") == b.name}
                pool = self.pool_now(b)                        # (a state only lowers it: min, never more)
                room = min(pool, pool if cap is None else cap) - len(mine | set(self.going.get(b.name, {})))
                if b.params.get("daemon"):           # the daemon's room, shared by every block it serves (SPEC §9.7)
                    room = min(room, self.e.daemons.free(b.params["daemon"]) - self.handing(b.params["daemon"]))
                if room <= 0:
                    continue
                for it in ordered(b, unblocked(self, b, self.ready(b, every, now)))[:room]:
                    self.stale = True
                    self.take(b, self.whole(ix, it))

    def pool_now(self, b) -> int:
        """The block's pool now: its ``pool:``, or its stock's level as the engine last read it (a stored value: no
        sensor runs here), at most its ``most``. Unread: 0, said once until it is read again (not said before the
        engine's first pass has loaded the readings: still 0 then)."""
        if b.pool_now is None:
            return b.pool
        v = self.e.get(b.pool_now)
        if poolnow.unread(v) and self.e.measured:
            if b.name not in self.unread:
                self.unread.add(b.name)
                self.e.say(f"{b.name}: its pool ({b.pool_now}) has no reading: it takes nothing new")
        else:
            self.unread.discard(b.name)
        return poolnow.now(b, v)

    def ready(self, b, every, now: float) -> list:
        """The items a block may take now, in the order it takes them: oldest in its first state first."""
        busy = self.going_items()
        got = []
        for i in every:
            if i.state not in b.takes.at or held(i.fields) or i.id in busy or not its.matches(i, b.takes.where):
                continue
            after = float((i.fields.get("lease") or {}).get("not_before") or 0)
            if after > now and i.id not in self.due_now:   # put off: looked at again when it falls due
                self.due = min(self.due, after)
                continue
            got.append(i)
        return sorted(got, key=lambda i: (b.takes.at.index(i.state), i.entered, i.first))

    def once(self, b, why: str) -> list[str]:
        """A run asked for by hand (``ergostat block NAME --now``): it leases the next item the block would take, and
        runs here, at once, whatever its pool; with nothing to take, nothing runs; under an operating state's pool 0,
        nothing runs either."""
        cap, capwhy = self.cap()
        if cap == 0:
            self.e.say(f"{b.name}: not run: {capwhy} (pool 0)")
            return []
        with self.lock:
            got = ordered(b, unblocked(self, b, self.ready(b, its.project(self.p.events, self.spec, b.takes.kind, transcript=False),
                                                          time.time())))
            started = self.take(b, got[0], inline=True) if got else None
        if started is None:
            self.e.say(f"{b.name}: nothing to take ({b.takes.kind} at {', '.join(b.takes.at)})")
            return []
        return self._work(*started, why=why)

    def take(self, b, it, inline: bool = False):
        self.due_now.discard(it.id)
        t = terms(self.spec, b)
        lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else {}
        fence = int(lease.get("fence") or 0) + 1
        run = uuid.uuid4().hex
        cause = it.moves[-1]["event"] if it.moves else None      # what brought it to the state it is taken from
        key = f"{b.name} {it.id}"
        with self.e.lock:                  # (the stop is set under this lock: a take that passes waits it out in close)
            if self.e.stop.is_set():
                return None                                       # ergostat is stopping: nothing more is taken
            self.e.running.add(key)
            self.ours.add(run)                                    # (before its write: a lease of ours is never missed)
        try:
            ev = self.p.events.add(TAKEN, item=it.id, source=SOURCE, causedby=cause,
                                   data={"item": it.id, "run": run, "block": b.name, "fence": fence, "ttl": t["ttl"],
                                         "max": t["attempts"], "back": it.state, "tier": t["tier"],
                                         "attempt": int(lease.get("attempts") or 0) + 1})
            now = its.one(self.p.events, self.spec, it.id)
            got = held(now.fields) if now else None
            back = (not got or got.get("holder") != run           # someone else took it first: the fold refused this one,
                    or self.spec.operating and self.entered_meanwhile(b, now, got, run, fence, inline))  # or given back
        except BaseException:
            with self.e.lock:
                self.e.running.discard(key)
            raise
        if back:
            self.ours.discard(run)
            with self.e.lock:
                self.e.running.discard(key)
            return None
        self.mine[run] = (b, it.id, fence)                        # (close() gives it back, whatever its run's end does)
        self.resources(ev)
        self.going.setdefault(b.name, {})[it.id] = {"run": run, "fence": fence, "block": b}
        if self.e.stop.is_set():                                  # it raced the stop: given back, not counted, not run
            self.give_back(b.name, it.id)
            with self.e.lock:
                self.e.running.discard(key)
            return None
        self.e.say(f"{b.name}: took {it.id} (lease {fence}, {t['ttl'] / 60:g} min)")
        item = {"id": it.id, "kind": it.kind, "state": it.state, "fields": {k: v for k, v in it.fields.items() if k != "lease"}}
        given = {"fence": fence, "ttl": t["ttl"], "expires": got.get("expires"), "attempt": int(lease.get("attempts") or 0) + 1,
                 "attempts": t["attempts"], "tier": t["tier"], "back": it.state}
        with self.e.lock:
            given["model"] = (self.e.spec, self.e.version)       # it runs to its end under the model it was taken under
        if inline:
            return b, item, given, run, ev["id"]
        threading.Thread(target=self._work, args=(b, item, given, run, ev["id"]), daemon=True).start()
        return None

    def _work(self, b, item: dict, lease: dict, run: str, taken: str, why: str = "item") -> list[str]:
        slot = self.e.slots.get(b.agent or "")
        out: dict = {}
        moved: list[str] = []
        try:
            if slot:
                slot.acquire()
            try:
                spec, version = lease.pop("model", (None, None))
                if self.e.stop.is_set():                       # taken just as ergostat stopped: not started
                    out["stopped"] = True
                    return moved
                moved = self.e.run_block(b, why, extra={"item": item, "lease": lease}, spec=spec, version=version,
                                         item=item["id"], fence=lease["fence"],
                                         run_id=run, cause=taken, outcome=out)
            except Exception as e:
                self.e.say(f"{b.name}: {type(e).__name__}: {e}")
                out.setdefault("note", f"{type(e).__name__}: {e}")
        finally:
            if slot:
                slot.release()
            with self.lock:                  # claimed under the lock, ended outside it: once, here or by give_back
                mine = self.going.get(b.name, {}).get(item["id"], {}).get("run") == run
                if mine:
                    self.going[b.name].pop(item["id"], None)
            if mine:                         # (its lease still held in the fold: a look counts it till it ends)
                try:
                    self.finish(b, item["id"], lease["fence"], run, out)
                except Exception as e:                         # the watchdog ends it later
                    self.e.say(f"{b.name}: ending the lease on {item['id']}: {type(e).__name__}: {e}")
            with self.e.lock:
                for s in self.e.after_acting(moved):
                    self.e.read_cause[s.series] = run
                    self.e.read_soon(s)
                self.e.running.discard(f"{b.name} {item['id']}")
                self.e.finished[b.name] = time.time()
        self.e.poke(b.name)
        return moved

    def give_back(self, block: str | None = None, item: str | None = None) -> None:
        """Ergostat stopping: each lease taken here and still going (or the one named) is given back, not counted, so
        that after a restart no item is left leased by a run that never ran, or never ended (the engine's ``close``)."""
        if not self.lock.acquire(timeout=self.e.lock_wait):    # (a look wedged: close never waits for good; the
            self.e.say("leases: not given back (the dispatcher is busy); they expire")   # next watchdog expires them)
            return
        try:                                                   # claimed under the lock (as _work does), ended outside it
            back = [(g["block"], i, g["fence"], g["run"]) for name, runs in self.going.items() for i in list(runs)
                    if (block, item) in ((None, None), (name, i)) and (g := runs.pop(i))]
            if block is None:                                  # and every lease taken here not ended yet (its run's
                back += [(b, i, f, run) for run, (b, i, f) in self.mine.copy().items()]   # own end failed, or under way)
        finally:
            self.lock.release()
        for b, i, fence, run in back:
            try:
                self.finish(b, i, fence, run, {"stopped": True})
            except Exception as e:                             # (the next engine's watchdog expires it)
                self.e.say(f"{b.name}: giving back {i}: {type(e).__name__}: {e}")

    def finish(self, b, item: str, fence: int, run: str, out: dict) -> None:
        """The run ended: its lease ends, ack or nack. Nothing, when its lease ended already (it expired). Read and
        written under one lock of its own (never waited on for good), so close()'s give-back and the run's own end
        never both end it; a look never waits on it."""
        if not self.ends.acquire(timeout=self.e.lock_wait):
            raise TimeoutError("another end of a lease is wedged")
        try:
            ev = self._finish(b, item, fence, run, out)
            self.mine.pop(run, None)
        finally:
            self.ends.release()
        if ev is not None:
            self.resources(ev)

    def _finish(self, b, item: str, fence: int, run: str, out: dict) -> dict | None:
        it = its.one(self.p.events, self.spec, item)
        lease = held(it.fields) if it else None
        if not lease or lease.get("fence") != fence or lease.get("holder") != run:
            self.ours.discard(run)                       # (ended already: expired, or given back from outside)
            return None
        data = {"run": run, "fence": fence, "exit": out.get("exit"), **({"note": out["note"]} if out.get("note") else {})}
        nack = out.get("nack")
        stopping = self.e.stop.is_set() or out.get("stopped")
        if nack is not None:
            data.update({"how": "nack", "why": nack.get("why") or "given back", **{k: nack[k] for k in ("after", "count", "news")
                                                                                     if nack.get(k) is not None}})
        elif moved_on(b, it):                    # (its lines moved it on as it ran: stopped after, the work stands)
            data["how"] = "ack"
        elif stopping:
            data.update({"how": "nack", "why": "stopped with ergostat", "count": False})
        else:
            data.update({"how": "nack", "why": out.get("note") or f"the run ended with {item} still {it.state}"})
        data.update(self.after(it, lease, data["how"] == "nack" and data.get("count", True) is not False,
                               it.state if data["how"] == "ack" else None))
        ev = self.p.events.add(ENDED, item=item, source=SOURCE, causedby=run, data=data)
        self.ours.discard(run)
        if data["how"] == "nack":
            after = its.one(self.p.events, self.spec, item)
            dead = after is not None and after.state == DEAD
            self.e.say(f"{b.name}: gave {item} back ({data['why']})" + (": a dead letter now" if dead else ""))
        return ev

    def resources(self, ev: dict) -> None:
        """What holds a resource as long as a lease, told at once (the engine's clock sweeps the same events later, for
        those it did not record itself): the workspace pools (SPEC §12k)."""
        spec = self.spec
        if not spec.workspaces:
            return
        try:
            from ..workspaces import leases as wl
            wl.on_event(self.p, spec, ev)
        except Exception as e:                                   # the sweep tries again
            self.e.say(f"workspaces: {type(e).__name__}: {e}")

    def after(self, it, lease: dict, counted: bool, stays: str | None = None) -> dict:
        """What a lease's end says of its item, for what holds a resource as long as the lease (SPEC §9.5): the item,
        the state it is left in, and whether that is terminal (its kind's last state, or a dead letter), so a
        working copy can be cleaned, or kept while the item waits (under review, back in the queue)."""
        if stays is None:
            n = int(lease.get("attempts") or 0) + (1 if counted else 0)
            stays = DEAD if counted and n >= int(lease.get("max") or 1) else (lease.get("back") or it.state)
        return {"item": it.id, "state": stays, "terminal": terminal(self.spec, it.kind, stays)}

    # ---- the watchdog

    def watch(self, now: float | None = None, mono: float | None = None) -> None:
        """Every held lease past its expiry: renewed by what its holder was seen to do since, or, on a second look
        ``grace(ttl)`` after the first, expired."""
        now = time.time() if now is None else now
        mono = time.monotonic() if mono is None else mono
        holding = False
        overdue: dict[tuple, float] = {}
        looked: set[str] = set()
        self.stale = True                                 # (read once a pass: what it records is about the item it looks at)
        try:
            for kind in self.kinds():
                for it in self.items_of(kind)[0]:
                    lease = held(it.fields)
                    holding = holding or lease is not None
                    looked.add(it.id)
                    if not lease or now <= float(lease.get("expires") or 0):
                        continue
                    try:
                        self.look(it, lease, now, mono, overdue)
                    except Exception as e:                 # (one item's trouble stops no other's look)
                        self.e.say(f"leases: the lease on {it.id}: {type(e).__name__}: {e}")
        finally:                                           # (the first looks kept, of the items not reached too)
            self.overdue = {**{k: v for k, v in self.overdue.items() if k[0] not in looked}, **overdue}
        self.holding = holding

    def look(self, it, lease: dict, now: float, mono: float, overdue: dict) -> None:
        """A held lease past its expiry: renewed by what its holder was seen to do since; else, a grace after the first
        look at this expiry, expired."""
        ttl = float(lease.get("ttl") or 0)
        seen = self.activity(it.id, lease)
        if seen is not None and seen > now - ttl:
            self.p.events.add(RENEWED, item=it.id, source=SOURCE, at=seen,
                              data={"run": lease["holder"], "fence": lease["fence"], "seen": "activity"})
            return
        key = (it.id, lease["fence"], lease.get("expires"))     # (renewed since: a first look again)
        first = overdue[key] = self.overdue.get(key, mono)
        if mono - first >= grace(ttl):                     # (a renewal asked in time may not be recorded yet)
            self.expire(it, lease, now, ttl)

    def expire(self, it, lease: dict, now: float, ttl: float) -> None:
        """The lease expires, unless the fold refuses it (renewed since it was judged): then nothing else is done. Its
        run, when this engine started it, is killed. Held by a run this engine did not take (a previous engine
        process's, its finish never recorded: a hard restart, a crash), its attempt is not counted."""
        fresh = its.one(self.p.events, self.spec, it.id)              # (the record now, not the look's index)
        now_held = held(fresh.fields) if fresh else None
        if (not now_held or now_held.get("fence") != lease["fence"]
                or float(now_held.get("expires") or 0) > float(lease.get("expires") or 0)):
            return                                                    # renewed, or ended, since the look: nothing written
        silent = now - float(lease.get("renewed") or lease.get("taken") or now)
        counted = lease["holder"] in self.ours
        ev = self.p.events.add(EXPIRED, item=it.id, source=SOURCE,
                               data={"run": lease["holder"], "fence": lease["fence"], "block": lease.get("block"),
                                     "silent": round(silent, 1), "ttl": ttl, "expires": lease.get("expires"),
                                     **({} if counted else {"count": False}), **self.after(it, lease, counted)})
        after = its.one(self.p.events, self.spec, it.id)
        if after is None or any(r["event"] == ev["id"] for r in after.refused):    # (renewed meanwhile: it holds on)
            return
        self.resources(ev)
        kill(self.e, lease["holder"], f"its lease on {it.id} expired: silent {silent:.0f}s, its TTL {ttl:g}s",
             it.id, lease["fence"], lease.get("block"))
        self.e.say(f"{lease.get('block')}: the lease on {it.id} expired (silent {silent / 60:.1f} min)"
                   + (": a dead letter now" if after.state == DEAD else ""))

    def activity(self, item: str, lease: dict) -> float | None:
        """The latest thing the holder was seen to do since its lease was renewed: a line of the item's transcript, an
        event it caused about anything, or an event about an item it started (its session)."""
        since = float(lease.get("renewed") or 0)
        run = lease["holder"]
        latest = None
        got = self.p.events.query(n=1, item=item, type="claude.*", since=since)
        if got:
            latest = got[-1]["time"]
        started = set()
        for e in self.p.events.caused_by(run):
            if e["time"] > since:
                latest = max(latest or 0.0, e["time"])
            if e.get("item") and e["item"] != item and "/" in e["item"] and not e["item"].startswith("ergostat."):
                started.add(e["item"])
        for other in sorted(started)[:20]:
            got = self.p.events.query(n=1, item=other, since=since)
            if got:
                latest = max(latest or 0.0, got[-1]["time"])
        return latest
