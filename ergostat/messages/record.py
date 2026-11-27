"""A message, recorded (SPEC §12h): an ``ergostat.message`` item, from whoever sent it.

Its id is ``ergostat.message/<short hash>``. Every step is an event about it: ``ergostat.message.received`` (from its
sender: the text verbatim, who, when, what it is about when they said, how it came), then from ergostat (or the
classifier block) ``.routed`` (what it matched, how, and the work it was routed to) or ``.unrouted`` (why nothing), and
then ``.delivered`` (each delivery: how, to which run, session, block or item), ``.queued`` (held for a session's next
step), ``.answered`` (what the work said back) and ``.missed`` (the work finished without it, and was redone). The
item, folded from them by its projection, is the message; the record is the only store."""

from __future__ import annotations

import hashlib
import json
import time
import uuid

from ..spec.ir import MESSAGE, message_kind

TEXT_MAX = 4000
STATES = ("received", "unrouted", "routed", "delivered", "answered")


class MessageError(ValueError):
    """A message that cannot be recorded (it says nothing)."""


def item_of(mid: str) -> str:
    return mid if mid.startswith(MESSAGE + "/") else f"{MESSAGE}/{mid}"


def short(mid: str) -> str:
    return mid.split("/", 1)[1] if mid.startswith(MESSAGE + "/") else mid


def about_list(about) -> list[str]:
    if about is None or about == "":
        return []
    if isinstance(about, str):
        return [x.strip() for x in about.split(",") if x.strip()]
    if isinstance(about, list | tuple):
        return [str(x).strip() for x in about if str(x).strip()]
    raise MessageError("about: an item (ticket/12) or a part (block.developer, stock.inbox), or a list of them")


def received(p, text, by: str = "owner", about=None, via: str = "cli", at: float | None = None,
             causedby: str | None = None) -> dict:
    """Record a message as received. Returns its event."""
    if not isinstance(text, str) or not text.strip():
        raise MessageError("a message says something: ergostat message \"that review can wait\"")
    text = text.strip()[:TEXT_MAX]
    now = time.time() if at is None else at
    mid = hashlib.sha1(json.dumps([text, by, now, uuid.uuid4().hex]).encode()).hexdigest()[:10]
    data = {"text": text, "by": str(by or "owner"), "sent": now, "about": about_list(about), "via": via,
            "outcome": "received"}
    return p.events.add(f"{MESSAGE}.received", item=item_of(mid), source=data["by"], data=data, at=now, causedby=causedby)


def step(p, mid: str, what: str, data: dict, by: str = "ergostat", causedby: str | None = None) -> dict:
    """One more step of a message: routed, unrouted, queued, delivered, answered, missed."""
    return p.events.add(f"{MESSAGE}.{what}", item=item_of(mid), source=by, data=data, causedby=causedby)


def fold(mid: str, events: list[dict]) -> dict:
    from ..spec import items as its
    it = its.fold(item_of(mid), events, message_kind())
    f = it.fields
    return {**f, "id": it.id, "state": it.state, "time": it.first, "last": it.last, "entered": it.entered,
            "moves": it.moves, "received_event": events[0]["id"] if events else None}


def stored(p, since: float | None = None, until: float | None = None, n: int | None = None) -> dict[str, dict]:
    """Every message received since then, folded, oldest first (the item index's table: ``projections.stored``). ``n``
    is kept for its callers: it capped the events read when they were read from the record, and caps nothing now."""
    from ..spec import projections
    return projections.stored(p, "message", since, until)


def get(p, mid: str) -> dict | None:
    evs = p.events.query(n=None, item=item_of(mid))
    if not evs:
        hit = [e for e in p.events.query(n=2000, type=f"{MESSAGE}.received") if short(e["item"]).startswith(mid)]
        if len(hit) != 1:
            return None
        evs = p.events.query(n=None, item=hit[0]["item"])
    return fold(evs[0]["item"], evs)
