"""The engine's dispatcher and watchdog for blocks that take items (SPEC §9.5).

- **Dispatch.** For each block that takes items: while nothing commands it, or what commands it is on, every item of
  its kind in one of its ``at`` states, not held, not put off (``not_before``), and matching its ``where``, is leased
  to a run of its own, oldest first, while the block's runs in flight (its leases held, from the fold, and the runs
  going here) are fewer than its ``pool``. It looks whenever the record has something new (an item reaching its
  state starts a run at once; the lease is caused by that event) and every second besides.
- **The run.** Given its item (its folded fields) and its lease in its input; ``ERGOSTAT_ITEM`` and ``ERGOSTAT_LEASE``
  (the fencing number; the holder is ``ERGOSTAT_RUN``) in its environment; its event lines are about its item by
  default. When it ends, its lease ends: ack when the work moved the item on (to a state of ``to``, or any but where
  it was taken from), nack otherwise (or when it said ``{"nack": ...}``), the why its exit or its own words.
- **The watchdog.** A held lease past its expiry is looked at once more: a line of the item's transcript, an event the
  holder caused about anything, or about an item the holder started (its session), since it was last renewed, renews
  it (``ergostat.lease.renewed``, at that time); otherwise it expires (``ergostat.lease.expired``). A run whose lease
  expired is not killed: what it says about the item afterwards is refused."""

from __future__ import annotations

import threading
import time
import uuid

from ..spec import items as its
from ..spec.ir import DEAD, LEASED
from . import ENDED, EXPIRED, RENEWED, TAKEN
from .fold import held
from .terms import terms

SOURCE = "ergostat"
LOOK = 0.25           # seconds between looks at the record for something new
EVERY = 1.0           # a look at every block's queue, and the watchdog's pass, at least this often


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
        self.going: dict[str, dict[str, dict]] = {}   # block → item → {run, fence}: the runs going here
        self.holding = False                          # whether the last watch found a lease held (one outlives its block)
        self.lock = threading.RLock()
        self.seq = 0

    @property
    def spec(self):
        """The model as it is now: a lease taken under an earlier one is still held, renewed and fenced as it was."""
        return self.e.spec

    @property
    def blocks(self) -> list:
        return [b for b in self.spec.blocks.values() if b.takes and b.machine]

    def kinds(self) -> list[str]:
        """The kinds whose leases are watched: every kind of the model's own (a lease outlives the block that took it)."""
        return [k for k in self.spec.items if not k.startswith("ergostat.")]

    # ---- the clock

    def run(self) -> None:
        last = 0.0
        while not self.e.stop.is_set():
            try:
                seq = self.p.events.last_seq()
                mono = time.monotonic()
                if seq != self.seq or mono - last >= EVERY:
                    self.seq = seq
                    if mono - last >= EVERY:
                        last = mono
                        if self.blocks or self.holding:      # (a model with no block that takes: nothing to watch)
                            self.watch()
                    self.tick()
            except Exception as e:                             # the next look tries again
                self.e.say(f"leases: {type(e).__name__}: {e}")
            self.e.stop.wait(LOOK)

    # ---- dispatch

    def going_items(self) -> set[str]:
        return {i for g in self.going.values() for i in g}

    def tick(self) -> None:
        """Lease what each block may take now, and start a run for each."""
        now = time.time()
        for b in self.blocks:
            if self.e.stop.is_set() or b.name in self.e.held:
                return
            cmd, _ = self.e.command_of(b)
            if cmd is not None and not cmd:                    # commanded, and nothing commands it now: it takes nothing
                continue
            with self.lock:
                every = its.project(self.p.events, self.spec, b.takes.kind, transcript=False)
                mine = {i.id for i in every if (held(i.fields) or {}).get("block") == b.name}
                room = b.pool - len(mine | set(self.going.get(b.name, {})))
                if room <= 0:
                    continue
                for it in self.ready(b, every, now)[:room]:
                    self.take(b, it)

    def ready(self, b, every, now: float) -> list:
        """The items a block may take now, in the order it takes them: oldest in its first state first."""
        busy = self.going_items()
        got = [i for i in every if i.state in b.takes.at and not held(i.fields) and i.id not in busy
               and float((i.fields.get("lease") or {}).get("not_before") or 0) <= now and its.matches(i, b.takes.where)]
        return sorted(got, key=lambda i: (b.takes.at.index(i.state), i.entered, i.first))

    def once(self, b, why: str) -> list[str]:
        """A run asked for by hand (``ergostat block NAME --now``): it leases the next item the block would take, and
        runs here, at once, whatever its pool; with nothing to take, nothing runs."""
        with self.lock:
            got = self.ready(b, its.project(self.p.events, self.spec, b.takes.kind, transcript=False), time.time())
            started = self.take(b, got[0], inline=True) if got else None
        if started is None:
            self.e.say(f"{b.name}: nothing to take ({b.takes.kind} at {', '.join(b.takes.at)})")
            return []
        return self._work(*started, why=why)

    def take(self, b, it, inline: bool = False):
        t = terms(self.spec, b)
        lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else {}
        fence = int(lease.get("fence") or 0) + 1
        run = uuid.uuid4().hex
        cause = it.moves[-1]["event"] if it.moves else None      # what brought it to the state it is taken from
        ev = self.p.events.add(TAKEN, item=it.id, source=SOURCE, causedby=cause,
                               data={"item": it.id, "run": run, "block": b.name, "fence": fence, "ttl": t["ttl"],
                                     "max": t["attempts"],
                                     "back": it.state, "tier": t["tier"], "attempt": int(lease.get("attempts") or 0) + 1})
        now = its.one(self.p.events, self.spec, it.id)
        got = held(now.fields) if now else None
        if not got or got.get("holder") != run:                   # someone else took it first: the fold refused this one
            return None
        self.going.setdefault(b.name, {})[it.id] = {"run": run, "fence": fence}
        self.e.say(f"{b.name}: took {it.id} (lease {fence}, {t['ttl'] / 60:g} min)")
        item = {"id": it.id, "kind": it.kind, "state": it.state, "fields": {k: v for k, v in it.fields.items() if k != "lease"}}
        given = {"fence": fence, "ttl": t["ttl"], "expires": got.get("expires"), "attempt": int(lease.get("attempts") or 0) + 1,
                 "attempts": t["attempts"], "tier": t["tier"], "back": it.state}
        with self.e.lock:
            self.e.running.add(f"{b.name} {it.id}")
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
                moved = self.e.run_block(b, why, extra={"item": item, "lease": lease}, spec=spec, version=version,
                                         item=item["id"], fence=lease["fence"],
                                         run_id=run, cause=taken, outcome=out)
            except Exception as e:
                self.e.say(f"{b.name}: {type(e).__name__}: {e}")
                out.setdefault("note", f"{type(e).__name__}: {e}")
        finally:
            if slot:
                slot.release()
            try:
                self.finish(b, item["id"], lease["fence"], run, out)
            except Exception as e:                                 # the watchdog ends it later
                self.e.say(f"{b.name}: ending the lease on {item['id']}: {type(e).__name__}: {e}")
            with self.lock:
                self.going.get(b.name, {}).pop(item["id"], None)
            with self.e.lock:
                for s in self.e.after_acting(moved):
                    self.e.read_cause[s.series] = run
                    self.e.read_soon(s)
                self.e.running.discard(f"{b.name} {item['id']}")
                self.e.finished[b.name] = time.time()
        self.e.evaluate()
        return moved

    def finish(self, b, item: str, fence: int, run: str, out: dict) -> None:
        """The run ended: its lease ends, ack or nack. Nothing, when its lease ended already (it expired)."""
        it = its.one(self.p.events, self.spec, item)
        lease = held(it.fields) if it else None
        if not lease or lease.get("fence") != fence or lease.get("holder") != run:
            return
        data = {"run": run, "fence": fence, "exit": out.get("exit"), **({"note": out["note"]} if out.get("note") else {})}
        nack = out.get("nack")
        stopping = self.e.stop.is_set() or out.get("stopped")
        if nack is not None:
            data.update({"how": "nack", "why": nack.get("why") or "given back", **{k: nack[k] for k in ("after", "count")
                                                                                     if nack.get(k) is not None}})
        elif stopping:
            data.update({"how": "nack", "why": "stopped with ergostat", "count": False})
        elif moved_on(b, it):
            data["how"] = "ack"
        else:
            data.update({"how": "nack", "why": out.get("note") or f"the run ended with {item} still {it.state}"})
        data.update(self.after(it, lease, data["how"] == "nack" and data.get("count", True) is not False,
                               it.state if data["how"] == "ack" else None))
        self.p.events.add(ENDED, item=item, source=SOURCE, causedby=run, data=data)
        if data["how"] == "nack":
            after = its.one(self.p.events, self.spec, item)
            dead = after is not None and after.state == DEAD
            self.e.say(f"{b.name}: gave {item} back ({data['why']})" + (": a dead letter now" if dead else ""))

    def after(self, it, lease: dict, counted: bool, stays: str | None = None) -> dict:
        """What a lease's end says of its item, for what holds a resource as long as the lease (SPEC §9.5): the item,
        the state it is left in, and whether that is terminal (its kind's last state, or a dead letter), so a
        working copy can be cleaned, or kept while the item waits (under review, back in the queue)."""
        if stays is None:
            n = int(lease.get("attempts") or 0) + (1 if counted else 0)
            stays = DEAD if counted and n >= int(lease.get("max") or 1) else (lease.get("back") or it.state)
        return {"item": it.id, "state": stays, "terminal": terminal(self.spec, it.kind, stays)}

    # ---- the watchdog

    def watch(self, now: float | None = None) -> None:
        """Every held lease past its expiry: renewed by what its holder was seen to do since, or expired."""
        now = time.time() if now is None else now
        holding = False
        for kind in self.kinds():
            for it in its.project(self.p.events, self.spec, kind, transcript=False):
                lease = held(it.fields)
                holding = holding or lease is not None
                if not lease or now <= float(lease.get("expires") or 0):
                    continue
                ttl = float(lease.get("ttl") or 0)
                seen = self.activity(it.id, lease)
                if seen is not None and seen > now - ttl:
                    self.p.events.add(RENEWED, item=it.id, source=SOURCE, at=seen,
                                      data={"run": lease["holder"], "fence": lease["fence"], "seen": "activity"})
                    continue
                silent = now - float(lease.get("renewed") or lease.get("taken") or now)
                self.p.events.add(EXPIRED, item=it.id, source=SOURCE,
                                  data={"run": lease["holder"], "fence": lease["fence"], "block": lease.get("block"),
                                        "silent": round(silent, 1), "ttl": ttl, **self.after(it, lease, True)})
                after = its.one(self.p.events, self.spec, it.id)
                dead = after is not None and after.state == DEAD
                self.e.say(f"{lease.get('block')}: the lease on {it.id} expired (silent {silent / 60:.1f} min)"
                           + (": a dead letter now" if dead else ""))
        self.holding = holding

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
