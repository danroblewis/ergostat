"""The hook between leases on items and the workspace pools (SPEC §12k). A run that works on an item under a lease
has ``ERGOSTAT_ITEM`` and ``ERGOSTAT_LEASE`` in its environment; the lease's events say when it ends:

- ``ergostat.lease.taken``: the item's work is under way again: a workspace held for it is in use again;
- ``ergostat.lease.ended`` and ``ergostat.lease.expired``: its workspaces are released (``pool.release``): held while
  the item is not finished, cleaned once it is.

The work item is the event's ``data.item``, else the event's own item; the lease, ``data.lease``, else the event's item
when it is a lease's (``ergostat.lease/...``). A run with no lease is its own: its workspace is released when it ends.
And a workspace held for an item is cleaned when the item finishes, whenever that is (``sweep``)."""

from __future__ import annotations

from . import pool as pl

TAKEN, ENDED, EXPIRED = "ergostat.lease.taken", "ergostat.lease.ended", "ergostat.lease.expired"
TYPES = f"{TAKEN},{ENDED},{EXPIRED}"


def work_item(ev: dict) -> str | None:
    d = ev.get("data") or {}
    it = d.get("item") or ev.get("item")
    return it if isinstance(it, str) and "/" in it and not it.startswith("ergostat.lease/") else None


def lease_of(ev: dict) -> str | None:
    d = ev.get("data") or {}
    if d.get("lease"):
        return str(d["lease"])
    it = ev.get("item") or ""
    return it if it.startswith("ergostat.lease/") else None


def finished(p, spec, item: str) -> bool:
    """Whether the item is in a state its kind finishes in (as ``messages: {done:}`` says, else as the record shows)."""
    from ..messages.route import done_states
    from ..spec import items as its
    k = its.kind_of(spec, item)
    if k is None or not k.states:
        return False
    got = its.project(p.events, spec, k.name)
    it = next((x for x in got if x.id == item), None)
    return bool(it and it.state in done_states(p, spec, k, got))


def fields_of(p, spec, item: str) -> dict:
    from ..spec import items as its
    evs = p.events.query(n=None, item=item)
    return its.fold(item, evs, its.kind_of(spec, item)).fields if evs else {}


def on_event(p, spec, ev: dict) -> list[dict]:
    """One lease event, taken to the pools."""
    item = work_item(ev)
    if item is None or not spec.workspaces:
        return []
    if ev["type"] == TAKEN:
        out = []
        for s in pl.held_by(p, spec, item):
            if s["state"] == "held":
                out.append(pl._record(p, s["pool"], s["slot"], "acquired",
                                      {**pl._keep(s), "how": "its lease taken again", "lease": lease_of(ev)}, ev["id"]))
        return out
    how = "expired" if ev["type"] == EXPIRED else "ended"
    done = finished(p, spec, item)
    return pl.release(p, spec, item, done, f"its lease {how}" + (", the item finished" if done else ", the item not finished"),
                      causedby=ev["id"], lease=lease_of(ev))


def run_ended(p, spec, item: str, run: str | None, lease: str | None) -> list[dict]:
    """A run ended: with no lease, it was its own, and its workspace is released now; under a lease, the lease's end
    releases it."""
    if lease or not spec.workspaces:
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
