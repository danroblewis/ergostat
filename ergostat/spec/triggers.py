"""Blocks started by an event (SPEC §9.3, *Started by an event*): ``on: {event: TYPE, where: {...}, emits: [...]}`` on a
``program`` or ``ai`` block runs it once for each recorded event of that type (a type, a list of them, or ``prefix.*``)
whose data matches ``where``, in the record's order, one run at a time.

- **Woken by the write.** The engine's loop wakes when the record is written (``notify.py``) and looks here
  (``Triggers.look``): no clock of its own. The record is the queue: each block keeps the ``seq`` of the last event it
  looked at, and resumes after the event its last run (or answered ask) was for when ergostat starts again.
- **Its cause.** The run's ``agent.started`` is caused by (``causedby``) the event, so what the run prints names it; the
  run is given it (``"trigger": "event"``, ``event``, ``ERGOSTAT_EVENT``).
- **No loops, by design.** ``emits:`` is the block's declared output set: ``check`` refuses a cycle of any length in
  the graph of who triggers whom, and a run's event lines (or ``event --add``) of a type it did not declare are refused.
- **A budget carried on the record.** Every run's ``agent.started`` carries its ``depth`` (the triggered runs in a row
  that led to it) and ``chain``, inherited from what caused it, whatever started it (an event, an item it takes, a
  command), read by exact, indexed lookups of its causes (``HOPS`` at most), never a scan; a cause not found is
  ``unknown``. At ``DEPTH`` a triggered block starts no more. A goal's crossing (``loop.*``) begins a fresh chain: a
  control loop closes through a measurement, which paces it.
- **A breaker per block.** More than ``most:`` triggered runs a minute (60) trips it: ``trigger.tripped``, an inbox
  entry, and no more runs from events until the owner resets it (the inbox, or ``ergostat block NAME --reset``).
- **Advise holds.** In ``mode: advise`` each event is asked about first (``block.advised``), and runs only when that ask
  is approved (an answer names its ask); restarted, the ask stands, not asked again.
- **Too old.** Events older than ``max-age:`` (1h) when looked at are passed over, recorded (``trigger.skipped``).
- **Gated** like any machine block: while what commands it (``goal:``, ``in: block.x``) is off, its events wait."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from types import SimpleNamespace

from ..runner import OWN_TYPES
from .ir import Trigger
from .items import matches

TRIGGER_KEYS = {"event", "where", "emits", "max-age", "most"}
TYPE = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*(\.\*)?$")
OWN = (*OWN_TYPES, "block.", "person.")   # ergostat's own record: no block says these, none starts one
DEPTH = 8              # the most triggered runs in a row, each caused by the one before
HOPS = 4               # how many causes back an event's run is looked for (an exact id lookup each)
WINDOW = 1000          # the most of the record's events one look reads for one block (the rest at the next)
LIMIT = 100            # the most matching events one look takes for one block (the rest at the next)
MAX_AGE = 3600.0       # events older than this when looked at are passed over (on.max-age)
MOST = 60              # triggered runs a minute that trip a block's breaker (on.most)
CHAIN = 16             # the blocks kept in a run's chain (the newest)
SOURCE = "ergostat"


def compile_on(c, m, what: str) -> Trigger | None:
    raw = m.get("on")
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = {"event": raw}
    elif not isinstance(raw, dict):
        c.err(f"{what}.on: a map: event: (the type that starts it, ticket.opened), where: (its data matches) and emits: "
              f"(the types its runs say)", m.at("on"), "not-a-map")
        return None
    else:
        c.keys(raw, TRIGGER_KEYS, f"{what}.on")
    types, emits = _types(raw.get("event")), _types(raw.get("emits", []), empty=True)
    if types is None or emits is None:
        c.err(f"{what}.on.{'event' if types is None else 'emits'}: an event type (lowercase words joined by dots: "
              f"ticket.opened), a list of them, or a prefix (ticket.*)", m.at("on"), "bad-type")
        return None
    where = raw.get("where") or {}
    if not isinstance(where, dict):
        c.err(f"{what}.on.where: a map of field: value (or a list of values), matched against the event's data",
              m.at("on"), "not-a-map")
        where = {}
    if where and hasattr(raw, "at"):
        c.where_values(where, raw["where"], f"{what}.on", what.replace(" ", ".", 1))
    age = c.duration(raw, "max-age", f"{what}.on", MAX_AGE) if hasattr(raw, "at") else MAX_AGE
    most = raw.get("most", MOST)
    if not isinstance(most, int) or isinstance(most, bool) or most < 1:
        c.err(f"{what}.on.most: how many runs a minute trip its breaker (a whole number, 1 or more)", m.at("on"),
              "bad-number")
        most = MOST
    if not emits:
        from .load import Problem
        c.problems.append(Problem("finding", f"{what}.on: no emits: (the event types its runs say), so every event line "
                                  f"it prints is refused; list them", m.at("on"), "trigger-no-emits"))
    return Trigger(types, dict(where), emits, age, most)


def _types(v, empty: bool = False) -> list[str] | None:
    v = [v] if isinstance(v, str) else v
    if not isinstance(v, list) or (not v and not empty) or not all(isinstance(t, str) and TYPE.match(t) for t in v):
        return None
    return [str(t) for t in v]


def overlap(a: str, b: str) -> bool:
    """Whether two types (each exact, or a prefix ending in ``.*``) can name the same event."""
    pa, pb = a.endswith(".*"), b.endswith(".*")
    if pa and pb:
        return a[:-1].startswith(b[:-1]) or b[:-1].startswith(a[:-1])
    if pa or pb:
        p, t = (a, b) if pa else (b, a)
        return t.startswith(p[:-1])
    return a == b


def check(c, spec) -> None:
    """A block started by events runs a program or a prompt, is started by them alone (not by every:, cron: or items it
    takes), on types ergostat does not write itself; and no chain of such blocks leads back to where it began."""
    for b in spec.blocks.values():
        if b.on is None:
            continue
        what = f"block {b.name}.on"
        if b.type not in ("program", "ai"):
            c.err(f"{what}: only a program or an ai block is started by an event", b.where, "bad-trigger")
        elif b.every or b.cron or b.takes:
            c.err(f"{what}: a block started by an event is started by it alone, not also by "
                  f"{'takes:' if b.takes else 'every: or cron:'}", b.where, "bad-trigger")
        elif own := [t for t in b.on.events + b.on.emits if any(overlap(t, x + "*") for x in OWN)]:
            c.err(f"{what}: {', '.join(own)} is ergostat's own record ({', '.join(x + '*' for x in OWN)}): no block says "
                  f"it, so none is started by it (start it on an event a block says, named in that block's emits:)", b.where,
                  "bad-trigger")
        else:
            continue
        b.on = None
    for cycle in loops(spec):
        c.err(f"block {cycle[0]}.on: its runs start themselves again, {' → '.join(cycle)} (each emits: a type the next "
              f"is on:); break the loop, or narrow a type", spec.blocks[cycle[0]].where, "trigger-loop")
        for n in cycle:
            spec.blocks[n].on = None


def loops(spec) -> list[list[str]]:
    """The cycles in the graph of blocks started by events (an edge from each to those its ``emits:`` can start;
    ``where:`` is not read, so any that might), one for each strongly connected part that has one, of any length."""
    on = {n: b.on for n, b in spec.blocks.items() if b.on is not None}
    nxt = {a: [b for b in on if any(overlap(x, y) for x in on[a].emits for y in on[b].events)] for a in on}
    colour: dict[str, int] = {}                  # 1: on the path; 2: done
    out: list[list[str]] = []
    for root in on:
        if root in colour:
            continue
        path, stack = [root], [iter(nxt[root])]
        colour[root] = 1
        while stack:
            n = next(stack[-1], None)
            if n is None:
                colour[path.pop()] = 2
                stack.pop()
            elif colour.get(n) == 1:
                out.append(path[path.index(n):] + [n])
            elif n not in colour:
                colour[n] = 1
                path.append(n)
                stack.append(iter(nxt[n]))
    return out


def declared(b, t: str) -> bool:
    """Whether a block started by events may say an event of type ``t`` (its ``emits:``)."""
    return any(overlap(t, e) for e in b.on.emits)


def undeclared(spec, block: str | None, types) -> str | None:
    """Why a run of ``block`` may not record these types (``event --add`` from a run, SPEC §9.3), or None."""
    b = spec.blocks.get(block or "") if spec is not None else None
    bad = [t for t in types if b is not None and b.on is not None and not declared(b, str(t))]
    return f"{', '.join(bad)} is not among what {block} emits: (on.emits: {b.on.emits or 'none'})" if bad else None


class Triggers:
    """The blocks started by events, looked at each time the engine's loop wakes."""

    def __init__(self, eng):
        self.e = eng
        self.at: dict[str, int] = {}             # block → the seq of the last event it looked at
        self.asked: dict[str, dict] = {}         # advised block → its ask: the event, its lineage, seq, approved
        self.lines: dict[str, tuple] = {}        # event id → (depth, chain, known) of what led to it (looked up once)
        self.recent: dict[str, deque] = {}       # block → when its latest triggered runs started (its breaker)
        self.tripped: set[str] = set()
        self.top = -1
        self.lock = threading.Lock()             # the loop looks; answers and resets come from another thread

    def look(self) -> None:
        with self.lock:
            self._look()

    def _look(self) -> None:
        e = self.e
        blocks = [b for b in e.spec.blocks.values() if b.on is not None and b.machine]
        if not blocks:
            return
        top = e.p.events.last_seq()
        if top == self.top:
            return                               # nothing new written since the last look
        self.top = top
        for b in blocks:
            if b.name not in self.at:
                self.at[b.name] = self.resume(b, top)
            ask = self.asked.get(b.name)
            if ask and b.mode != "advise":
                del self.asked[b.name]           # (no longer advised: what it asked about runs now)
            elif ask:
                if ask["approved"]:
                    self.approved(b, ask)        # approved, and not started yet: again
                continue                         # waiting for its ask's answer
            at = self.at[b.name]
            cmd, _ = e.command_of(b)
            if at >= top or b.name in self.tripped:
                continue
            if b.name in e.running or b.name in e.held or e.stop.is_set() or (cmd is not None and not cmd):
                self.top = -1                    # running, or gated off: its events wait for the next look
                continue
            end, old, now, n = min(top, at + WINDOW), [], time.time(), 0
            for ev in e.p.events.query(n=None, type=",".join(b.on.events), after_seq=at, before_seq=end + 1):
                if not matches(SimpleNamespace(fields=ev.get("data") or {}), b.on.where):
                    continue
                n += 1
                if n > LIMIT:
                    end = ev["seq"] - 1
                    break
                if ev["time"] < now - b.on.max_age:
                    old.append(ev["seq"])        # too old to act on: passed over, and said
                    continue
                line = self.lineage(ev.get("causedby"))
                if line[0] >= DEPTH:
                    self.stopped(b, ev, line)
                    continue
                if self.trip(b):
                    end = ev["seq"] - 1
                elif b.mode == "advise":
                    self.ask(b, ev, line)
                    end = ev["seq"] - 1
                else:
                    end = ev["seq"] if self.run(b, ev, line, "event") else ev["seq"] - 1
                break
            if old:
                e.p.events.add("trigger.skipped", item=b.name, source=SOURCE,
                               data={"events": len(old), "first": old[0], "last": old[-1], "max_age": b.on.max_age})
                e.say(f"{b.name}: {len(old)} event(s) older than its max-age passed over")
            self.at[b.name] = end
            if end < top:
                self.top = -1                    # more to look at: the next look reads on

    def run(self, b, ev: dict, line: tuple, why: str) -> bool:
        depth, chain, known = line
        lin = {"depth": depth + 1, "chain": [*chain, b.name][-CHAIN:], **({} if known else {"unknown": True})}
        if not self.e.start(b, why, extra={"event": dict(ev), "lineage": lin}, cause=ev["id"]):
            return False
        self.recent.setdefault(b.name, deque()).append(time.time())
        return True

    def lineage(self, cid: str | None) -> tuple[int, list, bool]:
        """(depth, chain, known) of what led to an event caused by ``cid``: from the run among its causes (its
        ``agent.started`` carries them), found by an exact id lookup of each, ``HOPS`` at most; a goal's crossing begins
        afresh; a cause not found, or too far back, is not known (its depth counted 0, the breaker still holds)."""
        ids, got = [], (0, [], True)
        while cid:
            if len(ids) >= HOPS:
                got = (0, [], False)             # too far back: not known
                break
            if cid in self.lines:
                got = self.lines[cid]
                break
            c = self.e.p.events.get(cid)
            if c is None:
                got = (0, [], False)
                break
            ids.append(cid)
            d = c.get("data") or {}
            if c.get("type") == "agent.started":
                got = (int(d.get("depth") or 0), list(d.get("chain") or []), not d.get("unknown"))
                break
            if str(c.get("type")).startswith("loop."):
                break                            # a goal's crossing: a control loop, paced by its readings
            cid = c.get("causedby")
        if len(self.lines) > 10000:
            self.lines.clear()
        for i in ids:
            self.lines[i] = got
        return got

    def of_run(self, b, ctx: dict, cause: str | None) -> dict:
        """What a run's ``agent.started`` carries of what led to it (SPEC §9.3): given, for a run started by an event;
        else inherited from its cause, whatever started it."""
        if isinstance(ctx.get("lineage"), dict):
            return ctx["lineage"]
        if not cause:
            return {}
        depth, chain, known = self.lineage(cause)
        return {"depth": depth, "chain": [*chain, b.name][-CHAIN:], **({} if known else {"unknown": True})}

    def trip(self, b) -> bool:
        """Its breaker: tripped by more than ``most`` triggered runs in a minute, recorded and asked about once."""
        q = self.recent.setdefault(b.name, deque())
        while q and q[0] < time.time() - 60.0:
            q.popleft()
        if len(q) < b.on.most:
            return False
        self.tripped.add(b.name)
        self.e.p.events.add("trigger.tripped", item=b.name, source=SOURCE, data={"runs": len(q), "most": b.on.most,
                                                                                  "window": 60.0})
        self.e.say(f"{b.name}: {len(q)} runs from events in a minute: its breaker tripped; no more until it is reset "
                   f"(ergostat block {b.name} --reset, or the inbox)")
        return True

    def reset(self, name: str) -> None:
        with self.lock:
            self.tripped.discard(name)
            self.recent.pop(name, None)
            self.top = -1
        self.e.wake.set()

    def stopped(self, b, ev: dict, line: tuple) -> None:
        self.e.p.events.add("trigger.stopped", item=b.name, source=SOURCE, causedby=ev["id"],
                            data={"event": ev["id"], "chain": line[1], "depth": line[0], "most": DEPTH})
        self.e.say(f"{b.name}: not started by {ev['type']} ({ev['id'][:8]}): {line[0]} triggered runs in a row led "
                   f"to it ({' → '.join(line[1])}), {DEPTH} at most")

    def ask(self, b, ev: dict, line: tuple) -> None:
        got = self.e.p.events.add("block.advised", item=b.name, source=SOURCE, causedby=ev["id"],
                                  data={"event": ev["id"], "event_type": ev["type"], "event_seq": ev["seq"],
                                        "how": f"ergostat block {b.name} --approve"})
        self.asked[b.name] = {"event": ev, "line": line, "seq": got["seq"], "approved": False}
        self.e.say(f"{b.name}: advised, waiting for approval (event {ev['type']} {ev['id'][:8]})")

    def answered(self, b, approved: bool, ask: int | None) -> None:
        """The owner's answer to its ask (``ask``: the seq of the ``block.advised`` it answers; another is stale and
        changes nothing): approved, it runs on that event (and keeps trying until it starts); denied, the next."""
        with self.lock:
            got = self.asked.get(b.name)
            if got is None or ask != got["seq"]:
                self.e.say(f"{b.name}: an answer to an ask that is not waiting ({ask}); nothing changes")
                return
            if approved:
                got["approved"] = True
                self.approved(b, got)
            else:
                del self.asked[b.name]
                self.at[b.name], self.top = got["event"]["seq"], -1
        self.e.wake.set()

    def approved(self, b, got: dict) -> None:
        if self.run(b, got["event"], got["line"], "approved"):
            del self.asked[b.name]
            self.at[b.name], self.top = got["event"]["seq"], -1
        else:
            self.top = -1                        # (it could not start now: the next look tries again)

    def resume(self, b, top: int) -> int:
        """Where a block's events are read from when ergostat starts: after the event its newest run (or denied ask) was
        for; an ask not answered stands (not asked again), and one approved and never run runs; else from now. Its
        breaker stays tripped until reset."""
        last = self.e.p.events.query(n=1, item=b.name, type="trigger.tripped,trigger.reset")
        if last and last[0]["type"] == "trigger.tripped":
            self.tripped.add(b.name)
        answers: dict = {}
        for x in reversed(self.e.p.events.query(n=50, item=b.name,
                                                type="agent.started,block.advised,block.approved,block.denied")):
            d = x.get("data") or {}
            if x["type"] in ("block.approved", "block.denied"):
                answers.setdefault(d.get("ask"), x["type"])
                continue
            if not isinstance(d.get("event_seq"), int):
                continue
            if x["type"] == "agent.started":
                return d["event_seq"]
            said = answers.get(x["seq"])
            ev = self.e.p.events.get(d.get("event") or "") if said != "block.denied" else None
            if ev is None:
                return d["event_seq"]            # denied (or its event is gone): the next
            self.asked[b.name] = {"event": ev, "line": self.lineage(ev.get("causedby")), "seq": x["seq"],
                                  "approved": said == "block.approved"}
            return d["event_seq"] - 1
        return top
