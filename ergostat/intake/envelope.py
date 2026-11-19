"""One event or a batch, pushed: the envelope a block's output lines use, checked, then recorded in one write, so the
engine's waiters wake on it at once (``notify.py``) and the item index folds it on their next look.

    {"event": "ticket.found", "item": "ticket/SCRUM-12", "data": {"title": "..."}}
    [{"event": ...}, {"event": ..., "item": ..., "patch": [...]}, {"event": ..., "id": "jira-10023-1700000000"}]

``type`` is taken for ``event``. ``id`` is the caller's: an event already recorded with it is not recorded again
(a webhook delivered twice). ``source`` is who pushed (a hook's name, else ``push``); ``causedby`` a run's id, when a
step pushes. An event type is lowercase words joined by dots, never ergostat's own (``agent.``, ``loop.``, ...)."""

from __future__ import annotations

import json
import time
import uuid

MOST = 1000                   # events in one push


class Refused(ValueError):
    """The push as a whole is not taken: nothing of it is recorded."""


def parse(body) -> list[dict]:
    """The events in a push: its JSON (bytes or text) or what it decoded to."""
    if isinstance(body, (bytes, str)):
        try:
            body = json.loads(body or b"null")
        except ValueError as e:
            raise Refused(f"not JSON ({e})") from None
    if isinstance(body, dict) and isinstance(body.get("events"), list):
        body = body["events"]
    evs = body if isinstance(body, list) else [body]
    if not evs or not all(isinstance(e, dict) for e in evs):
        raise Refused('an event ({"event": "ticket.found", "item": "ticket/12", "data": {...}}) or a list of them')
    if len(evs) > MOST:
        raise Refused(f"{len(evs)} events in one push: at most {MOST}")
    return evs


def check(e: dict, i: int = 0) -> dict:
    """One event, as ``Events.add_many`` takes it; Refused (with where it is in the batch) when it is not one."""
    from ..runner import OWN_TYPES, TYPE_NAME
    from ..store import ChangesetError, changeset
    where = f"event {i}: " if i else ""
    t = e.get("event", e.get("type"))
    if not isinstance(t, str) or not TYPE_NAME.match(t) or t.startswith((*OWN_TYPES, "block.", "person.")):
        raise Refused(f"{where}{t!r}: an event type is lowercase words joined by dots (ticket.opened), and not ergostat's own")
    unknown = set(e) - {"event", "type", "item", "data", "patch", "set", "id", "source", "causedby"}
    if unknown:
        raise Refused(f"{where}unknown keys {sorted(unknown)} (an event: event, item, data or patch or set, id)")
    item, data = e.get("item"), e.get("data")
    if item is not None and not isinstance(item, str):
        raise Refused(f"{where}item: an id, like ticket/12")
    if data is not None and not isinstance(data, dict):
        raise Refused(f"{where}data: a JSON object")
    try:
        change = changeset(data, e.get("patch"), e.get("set"))
    except ChangesetError as err:
        raise Refused(f"{where}{err}") from None
    if change and (not isinstance(item, str) or "/" not in item):
        raise Refused(f"{where}a patch or a set changes an item: name it (an id with a /, ticket/12)")
    out = {"type": t, "item": item, "data": data or {}}
    for k in ("patch", "set", "id", "causedby"):
        if e.get(k) is not None:
            out[k] = str(e[k]) if k in ("id", "causedby") else e[k]
    if e.get("source") is not None:
        out["source"] = str(e["source"])
    return out


def record(p, evs: list[dict], source: str = "push", causedby: str | None = None) -> dict:
    """Check every event, then record them all in one write (none when one is refused). What came of it: how many were
    new (an ``id`` recorded before is not recorded again), and each event's id."""
    rows = [check(e, i) for i, e in enumerate(evs)]
    now = time.time()
    for r in rows:
        r.setdefault("source", source)
        if causedby and not r.get("causedby"):
            r["causedby"] = causedby
    if len(rows) == 1:                                   # one: recorded as ``event --add`` records it, its seq known
        r = rows[0]
        ev = p.events.add(r["type"], item=r.get("item"), source=r["source"], data=r.get("data"), causedby=r.get("causedby"),
                          id=r.get("id"), patch=r.get("patch"), set=r.get("set"))
        return {"recorded": 0 if ev.get("seq") is None else 1, "ids": [ev["id"]], "time": ev["time"], "events": [ev]}
    for r in rows:
        r.setdefault("id", uuid.uuid4().hex)
        r["at"] = now
    new = p.events.add_many(rows, new=False)
    return {"recorded": new, "ids": [r["id"] for r in rows], "time": now}
