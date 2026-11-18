"""The hook between leases on items (SPEC §9.5) and the workspace pools (SPEC §12k). A run that works on an item under
a lease has ``ERGOSTAT_ITEM`` and ``ERGOSTAT_LEASE`` (the lease's fencing number) in its environment, and its workspace
is recorded with that fence. The lease events, about the item, say the rest (``data``: ``item``, ``run``, ``fence``;
an end also ``state`` and ``terminal``):

- ``ergostat.lease.taken``: the item's work is under way again: a workspace held for it is in use again, under the new
  fence (the run that took the lease acquires it as it starts);
- ``ergostat.lease.ended`` and ``ergostat.lease.expired``: the workspace the lease's fence holds is released
  (``pool.release``): held while the item is not finished (under review, or back in the queue), cleaned once it is
  (``terminal``). A lease that expired while its run still goes on fences the workspace: the next fence takes it, and
  nothing the old run asks for after is let through (``fenced``).

An event whose fence is older than the workspace's is about a lease that is over, and changes nothing, so the events
may be taken more than once (the dispatcher, then the clock's sweep). A run with no lease is its own: its workspace is
released when it ends. A workspace held for an item is cleaned when the item finishes, whenever that is (``sweep``)."""

from __future__ import annotations

from ..leases import ENDED, EXPIRED, TAKEN
from . import pool as pl

TYPES = f"{TAKEN},{ENDED},{EXPIRED}"


def work_item(ev: dict) -> str | None:
    d = ev.get("data") or {}
    it = d.get("item") or ev.get("item")
    return it if isinstance(it, str) and "/" in it and not it.startswith("ergostat.") else None


def fence_of(value) -> int | None:
    """A lease's fencing number, as an event's data or a run's ``ERGOSTAT_LEASE`` gives it, or None."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def finished(p, spec, item: str) -> bool:
    """Whether the item is in a state its kind finishes in: as ``messages: {done:}`` says, else its last state or a
    dead letter (as a lease's end says ``terminal``). A state between, a review, is not finished: its work is kept."""
    from ..leases.dispatch import terminal
    from ..spec import items as its
    k = its.kind_of(spec, item)
    if k is None or not k.states:
        return False
    it = its.one(p.events, spec, item)
    if it is None or not it.state:
        return False
    if k.name in spec.messages.done:
        return it.state in spec.messages.done[k.name]
    return terminal(spec, k.name, it.state)


def fields_of(p, spec, item: str) -> dict:
    from ..spec import items as its
    evs = p.events.query(n=None, item=item)
    return its.fold(item, evs, its.kind_of(spec, item)).fields if evs else {}


def run_going(p, run: str | None) -> bool:
    """Whether a run has started and not yet ended (no ``agent.ran`` or ``agent.failed`` caused by it)."""
    if not run:
        return False
    return not any(e["type"] in ("agent.ran", "agent.failed") for e in p.events.caused_by(run))


def on_event(p, spec, ev: dict) -> list[dict]:
    """One lease event, taken to the pools."""
    item = work_item(ev)
    if item is None or not spec.workspaces:
        return []
    d = ev.get("data") or {}
    fence = fence_of(d.get("fence"))
    if ev["type"] == TAKEN:
        out = []
        for pool in spec.workspaces.values():
            with pl.locked(pl.folder(p, spec, pool)):            # (the run that took it acquires it under the same lock)
                for s in pl.slots(p, spec, pool).values():
                    had = fence_of(s.get("lease"))
                    if s.get("item") != item or s["state"] != "held" or (fence is not None and had is not None
                                                                         and fence <= had):
                        continue                                 # not its, or an older lease's, or this one's already
                    out.append(pl._record(p, pool.name, s["slot"], "acquired",
                                          {**pl._keep(s), "how": "its lease taken again", "run": d.get("run"),
                                           "lease": fence}, ev["id"]))
        return out
    how = "expired" if ev["type"] == EXPIRED else "ended"
    done = bool(d["terminal"]) if "terminal" in d else finished(p, spec, item)
    why = f"its lease {how}" + (f" ({d['state']})" if d.get("state") else "")
    why += ", the item finished" if done else ", the item not finished"
    fenced = None
    if how == "expired" and not done and run_going(p, d.get("run")):
        fenced = {"run": d.get("run"), "fence": fence}
        why += f"; its run goes on, fenced (lease {fence}): the next lease takes it"
    return pl.release(p, spec, item, done, why, causedby=ev["id"], lease=fence, fenced=fenced)


def run_ended(p, spec, item: str, run: str | None, lease) -> list[dict]:
    """A run ended: with no lease, it was its own, and its workspace is released now; under a lease, the lease's end
    releases it."""
    if fence_of(lease) is not None or not spec.workspaces:
        return []
    done = finished(p, spec, item)
    return pl.release(p, spec, item, done, "its run ended" + (", the item finished" if done else ", the item not finished"),
                      causedby=run)


def sweep(p, spec, after: int = 0) -> int:
    """The lease events since ``after`` (a seq), each taken to the pools; then each workspace held for an item that has
    finished since, cleaned. Returns the newest seq seen."""
    if not spec.workspaces:
        return after
    for ev in p.events.query(n=None, type=TYPES, after_seq=after):
        after = max(after, ev["seq"] or after)
        on_event(p, spec, ev)
    for pool in spec.workspaces.values():
        for s in pl.slots(p, spec, pool).values():
            if s["state"] == "held" and s.get("item") and finished(p, spec, s["item"]):
                pl.release(p, spec, s["item"], True, "its item finished")
    return after
