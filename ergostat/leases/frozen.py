"""A frozen window on a block's queue (SPEC §9.5, ``takes: {frozen: {first: N, urgent: FIELD}}``): the first N items the
block would take keep their order when new work arrives or the queue is re-ranked; an item whose FIELD says who made it
urgent and why (``{by: ..., why: ...}``) goes ahead of them, and the dispatcher records that it did.

One rule, ``arrange``, for the dispatcher (``order``) and the completion estimates (``eta._Run.pick``), so the forecast
takes items in the order the block will. The list in force is the record's: the newest ``block.frozen`` event about
``ergostat.frozen/BLOCK`` by ``seq``, written by the dispatcher only when the window changes (``settle``, after a
look's takes: a taken item leaves it). Off unless declared."""

from __future__ import annotations

from ..spec.items import SNAPSHOT

LIST = "block.frozen"
BROKEN = "block.frozen.broken"
MOST = 200                 # the window's length at most (its ids are one event)


def about(block: str) -> str:
    return f"ergostat.frozen/{block}"


def urgent(fields: dict, field: str) -> dict | None:
    """Who made it urgent and why, when its ``field`` says both (``{by, why}``, words); else None: it waits its turn (a
    bare flag, or one missing either, overrides nothing)."""
    v = fields.get(field) if field and isinstance(fields, dict) else None
    if not isinstance(v, dict):
        return None
    by, why = v.get("by"), v.get("why")
    if isinstance(by, str) and by.strip() and isinstance(why, str) and why.strip():
        return {"by": by.strip()[:200], "why": why.strip()[:500]}
    return None


def arrange(plain: list[str], held: list[str], first: int, hurry) -> tuple[list[str], list[str]]:
    """The take order, from ``plain`` (the ids waiting, in the block's plain order) and ``held`` (the list in force):
    the urgent (``hurry``) first, in plain order; then the window: the list's items still waiting, in its order, filled
    to ``first`` from the plain order; then the rest in plain order. Returns (the take order, the window now)."""
    first = max(1, min(MOST, int(first)))
    there, hurry = set(plain), set(hurry)
    kept = [i for i in dict.fromkeys(held) if i in there and i not in hurry]
    k = set(kept)
    window = (kept + [i for i in plain if i not in hurry and i not in k])[:first]
    w = set(window)
    return [i for i in plain if i in hurry] + window + [i for i in plain if i not in hurry and i not in w], window


def in_force(events, block: str, until: float | None = None) -> list[str]:
    """The list in force for ``block`` (at ``until``): the newest ``block.frozen`` by ``seq`` (or, rolled up, its
    snapshot's), [] when none was written. A list not of ids is an error, raised: the caller takes its plain order."""
    got = events.query(n=1, type=f"{LIST},{SNAPSHOT}", item=about(block), until=until)
    if not got:
        return []
    e = got[-1]
    ids = (e.get("set") or {}).get("items", []) if e["type"] == SNAPSHOT else (e.get("data") or {}).get("items")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError(f"{LIST} {e.get('seq')}: its items are not a list of ids")
    return ids


def order(d, b, got: list, source: str) -> tuple[list, dict]:
    """The dispatcher's: ``got`` (the items it may take, in its plain order) in the frozen window's order, the window
    kept for ``settle`` to write once the look's takes are known; and each urgent item → the record of its override
    ({by, why, ahead}), when frozen items wait. A list that cannot be read: the plain order, said (a lost preference,
    never a stopped block)."""
    fz = b.takes.frozen
    said = d.__dict__.setdefault("frozen_said", set())
    pending = d.__dict__.setdefault("frozen_pending", {})
    pending.pop(b.name, None)
    try:
        held = in_force(d.p.events, b.name)
    except Exception as e:  # noqa: BLE001 - said, and the block takes by its plain order
        if (b.name, "unread") not in said:
            said.add((b.name, "unread"))
            d.e.say(f"{b.name}: frozen window not read ({type(e).__name__}: {e}): plain order")
        return got, {}
    said.discard((b.name, "unread"))
    hurry = {}
    for i in got:
        u = urgent(i.fields, fz.urgent)
        if u:
            hurry[i.id] = u
        elif fz.urgent and i.fields.get(fz.urgent) not in (None, "", False) and (b.name, i.id) not in said:
            said.add((b.name, i.id))
            d.e.say(f"{b.name}: {i.id}'s {fz.urgent} does not say by: and why:, so it waits its turn")
    ids, window = arrange([i.id for i in got], held, fz.first, hurry)
    pending[b.name] = (held, window)
    by = {i.id: i for i in got}
    return [by[i] for i in ids], {i: {**u, "ahead": window} for i, u in hurry.items() if window}


def settle(d, b, taken, source: str) -> None:
    """After a look's takes (under the dispatcher's lock, the list's only writer): the window ``order`` made, less the
    items taken (an item leaves the window when it is taken, SPEC §9.5: one back in its state later waits as any
    other), written when it differs from the list in force. Nothing kept (an unread list): nothing written."""
    got = d.__dict__.get("frozen_pending", {}).pop(b.name, None)
    if got is None:
        return
    held, window = got
    gone = set(taken)
    window = [i for i in window if i not in gone]
    if window != held:
        d.p.events.add(LIST, item=about(b.name), source=source, data={"block": b.name, "items": window})


def broken(d, b, item: str, rec: dict, source: str) -> None:
    """An urgent item taken ahead of the frozen window: who, why, and the items it went ahead of."""
    d.p.events.add(BROKEN, item=about(b.name), source=source, data={"block": b.name, "urgent": item, **rec})
    d.e.say(f"{b.name}: took {item} ahead of its frozen window ({rec['by']}: {rec['why']})")
