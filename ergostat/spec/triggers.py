"""Blocks started by an event (SPEC §9.3, *Started by an event*): ``on: {event: TYPE, where: {...}, emits: [...]}`` on a
``program`` or ``ai`` block runs it once for each recorded event of that type (a type, a list of them, or ``prefix.*``)
whose data matches ``where``, in the record's order, one run at a time.

- **Woken by the write.** The engine's loop wakes when the record is written (``notify.py``) and looks here
  (``Triggers.look``): no clock of its own. The record is the queue: each block keeps the ``seq`` of the last event it
  looked at, and resumes after the event its last run (or answered ask) was for when ergostat starts again.
- **Its cause.** The run's ``agent.started`` is caused by (``causedby``) the event, so what the run prints names it; the
  run is given it (``"trigger": "event"``, ``event``, ``ERGOSTAT_EVENT``).
- **No loops, by design.** ``emits:`` says the types its runs print; ``check`` refuses a cycle of any length in the
  graph of who triggers whom, and a run's event lines of a type it did not declare are refused. What still loops at run
  time (``$ERGOSTAT_CMD event --add`` from a run, which the graph cannot see) is stopped by a budget carried on the
  record: each triggered run's ``agent.started`` carries its ``chain`` of triggered blocks, read from the run that
  caused its event by an exact, indexed lookup (``HOPS`` at most), never a scan; at ``DEPTH`` nothing more starts.
- **Advise holds.** In ``mode: advise`` each event is asked about first (``block.advised``), and runs only when approved.
- **Gated** like any machine block: while what commands it (``goal:``, ``in: block.x``) is off, its events wait."""

from __future__ import annotations

import re
import threading
from types import SimpleNamespace

from ..runner import OWN_TYPES
from .ir import Trigger
from .items import matches

TRIGGER_KEYS = {"event", "where", "emits"}
TYPE = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*(\.\*)?$")
OWN = (*OWN_TYPES, "block.", "person.", "trigger.")   # ergostat's own record: no block says these, none starts one
DEPTH = 8              # the most triggered runs in a row, each caused by the one before
HOPS = 4               # how many causes back an event's run is looked for (an exact id lookup each)
WINDOW = 1000          # the most of the record's events one look reads for one block (the rest at the next)
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
    return Trigger(types, dict(where), emits)


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
                  f"it, so none is started by it (to run after a block, command it: out: block.NAME)", b.where,
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


class Triggers:
    """The blocks started by events, looked at each time the engine's loop wakes."""

    def __init__(self, eng):
        self.e = eng
        self.at: dict[str, int] = {}             # block → the seq of the last event it looked at
        self.asked: dict[str, tuple] = {}        # advised block → (the event it asked about, its chain)
        self.chains: dict[str, list] = {}        # event id → the triggered blocks that led to it (looked up once)
        self.top = -1
        self.lock = threading.Lock()             # the loop looks; an answer to an ask comes from another thread

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
            if b.name in self.asked and b.mode != "advise":
                del self.asked[b.name]               # (no longer advised: what it asked about runs now)
            at = self.at.get(b.name)
            if at is None:
                at = self.at[b.name] = self.resume(b, top)
            if at >= top or b.name in self.asked:
                continue                         # all looked at, or waiting for its ask's answer
            cmd, _ = e.command_of(b)
            if b.name in e.running or b.name in e.held or e.stop.is_set() or (cmd is not None and not cmd):
                self.top = -1                    # running, or gated off: its events wait for the next look
                continue
            end = min(top, at + WINDOW)
            for ev in e.p.events.query(n=None, type=",".join(b.on.events), after_seq=at, before_seq=end + 1):
                if not matches(SimpleNamespace(fields=ev.get("data") or {}), b.on.where):
                    continue
                chain = self.chain(ev)
                if len(chain) >= DEPTH:
                    self.stopped(b, ev, chain)
                    continue
                if b.mode == "advise":
                    self.ask(b, ev, chain)
                    end = ev["seq"] - 1
                elif not self.run(b, ev, chain, "event"):
                    end = ev["seq"] - 1
                else:
                    end = ev["seq"]
                break
            self.at[b.name] = end
            if end < top:
                self.top = -1                    # more to look at: the next look reads on

    def run(self, b, ev: dict, chain: list, why: str) -> bool:
        return self.e.start(b, why, extra={"event": dict(ev), "chain": [*chain, b.name]}, cause=ev["id"])

    def chain(self, ev: dict) -> list:
        """The triggered blocks whose runs led to this event, oldest first: read from the run that caused it (its
        ``agent.started`` carries its chain), found by an exact id lookup of each cause, ``HOPS`` at most."""
        ids, cid, got = [], ev.get("causedby"), []
        while cid and len(ids) < HOPS:
            if cid in self.chains:
                got = self.chains[cid]
                break
            c = self.e.p.events.get(cid)
            if c is None:
                break
            ids.append(cid)
            if c.get("type") == "agent.started":
                got = list((c.get("data") or {}).get("chain") or [])
                break
            cid = c.get("causedby")
        if len(self.chains) > 10000:
            self.chains.clear()
        for i in ids:
            self.chains[i] = got
        return got

    def stopped(self, b, ev: dict, chain: list) -> None:
        self.e.p.events.add("trigger.stopped", item=b.name, source=SOURCE, causedby=ev["id"],
                            data={"event": ev["id"], "chain": chain, "depth": len(chain), "most": DEPTH})
        self.e.say(f"{b.name}: not started by {ev['type']} ({ev['id'][:8]}): {len(chain)} triggered runs in a row led "
                   f"to it ({' → '.join(chain)}), {DEPTH} at most")

    def ask(self, b, ev: dict, chain: list) -> None:
        self.asked[b.name] = (ev, chain)
        self.e.p.events.add("block.advised", item=b.name, source=SOURCE, causedby=ev["id"],
                            data={"event": ev["id"], "event_type": ev["type"], "event_seq": ev["seq"],
                                  "how": f"ergostat block {b.name} --approve"})
        self.e.say(f"{b.name}: advised, waiting for approval (event {ev['type']} {ev['id'][:8]})")

    def answered(self, b, approved: bool) -> None:
        """The owner's answer to its ask: approved, it runs on that event; denied, it goes on to the next."""
        with self.lock:
            got = self.asked.get(b.name)
            if got is None or (approved and not self.run(b, got[0], got[1], "approved")):
                return                           # nothing asked; or it could not start now, and the ask stands
            del self.asked[b.name]
            self.at[b.name], self.top = got[0]["seq"], -1
        self.e.wake.set()

    def resume(self, b, top: int) -> int:
        """Where a block's events are read from when ergostat starts: after the event its newest run (or denied ask) was
        for; at an ask not answered, or approved and never run, so it is asked again; else from now."""
        answer = None
        for x in reversed(self.e.p.events.query(n=50, item=b.name,
                                                type="agent.started,block.advised,block.approved,block.denied")):
            seq = (x.get("data") or {}).get("event_seq")
            if x["type"] in ("block.approved", "block.denied"):
                answer = answer or x["type"]
            elif isinstance(seq, int):
                return seq if x["type"] == "agent.started" or answer == "block.denied" else seq - 1
        return top
