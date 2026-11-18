"""A gated action, recorded (SPEC §12k): an ``ergostat.action`` item, ``ergostat.action/<short hash>``. Its events:
``ergostat.action.requested`` (by the session's block: the action, its class and gate, its arguments, the command
rendered, the block, run, session, work item and folder), then ``.approved`` (by the owner, or ``gate`` for an
``auto`` one) or ``.denied`` (by the owner, or ``gate``), then ``.ran`` or ``.failed`` (its exit and output), and
``.delivered`` (its result given to the session, the program's run that asked, or the block's next run); a program's
action held and asked for again by a later run is ``.reasked`` (that run, and its lease's ``fence``). The record is the only store."""

from __future__ import annotations

import hashlib
import json
import time
import uuid

from ..spec.ir import ACTION, ACTIONS, action_kind

WEEK = 7 * 86400.0
GATE = "gate"                     # who approved or denied, when no person did


def item_of(aid: str) -> str:
    return aid if aid.startswith(ACTION + "/") else f"{ACTION}/{aid}"


def short(aid: str) -> str:
    return aid.split("/", 1)[1] if aid.startswith(ACTION + "/") else aid


def new_id(name: str) -> str:
    return item_of(hashlib.sha1(json.dumps([name, time.time(), uuid.uuid4().hex]).encode()).hexdigest()[:10])


def step(p, aid: str, what: str, data: dict, by: str = "ergostat", causedby: str | None = None) -> dict:
    return p.events.add(f"{ACTION}.{what}", item=item_of(aid), source=by, data=data, causedby=causedby)


def fold(aid: str, events: list[dict]) -> dict:
    from ..spec import items as its
    it = its.fold(item_of(aid), events, action_kind())
    return {**it.fields, "id": it.id, "state": it.state, "time": it.first, "last": it.last, "entered": it.entered,
            "moves": it.moves}


def get(p, aid: str) -> dict | None:
    evs = p.events.query(n=None, item=item_of(aid))
    if not evs:                                            # a short prefix of its id will do
        hit = {e["item"] for e in p.events.query(n=2000, type=f"{ACTION}.requested") if short(e["item"]).startswith(short(aid))}
        if len(hit) != 1:
            return None
        evs = p.events.query(n=None, item=hit.pop())
    return fold(evs[0]["item"], evs)


def stored(p, since: float | None = None, until: float | None = None) -> dict[str, dict]:
    """Every action requested since then, folded, oldest first."""
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{ACTION}.*", until=until):
        by.setdefault(e["item"], []).append(e)
    out = {}
    for item, es in by.items():
        if es[0]["type"] != f"{ACTION}.requested" or (since is not None and es[0]["time"] < since):
            continue
        out[item] = fold(item, es)
    return out


def about(p, item: str) -> list[dict]:
    """The actions asked for about one work item (or by one session or block run), newest first."""
    return sorted((a for a in stored(p).values() if item in (a.get("item"), a.get("session"), a.get("block"))),
                  key=lambda a: -a["time"])


def counts(p, now: float | None = None, cls: str | None = None, since: float | None = None) -> dict[str, float]:
    """Per class (or all): held now; approved by the owner, let through by the gate (auto), denied, ran and failed
    over the last week."""
    now = time.time() if now is None else now
    since = now - WEEK if since is None else since
    out = {"held": 0, "approved": 0, "auto": 0, "denied": 0, "ran": 0, "failed": 0}
    for a in stored(p, until=now).values():
        if cls is not None and a.get("class") != cls:
            continue
        if a["state"] == "requested":
            out["held"] += 1
        for mv in a["moves"]:
            if mv["time"] < since:
                continue
            if mv["to"] == "approved":
                out["auto" if a.get("approved_by") == GATE else "approved"] += 1
            elif mv["to"] in ("denied", "ran", "failed"):
                out[mv["to"]] += 1
    return {k: float(v) for k, v in out.items()}


def by_class(p, now: float | None = None) -> dict[str, dict[str, float]]:
    classes = sorted({a.get("class") or a.get("action") for a in stored(p).values()} - {None})
    return {c: counts(p, now, c) for c in classes}


def measure(p, name: str, now: float | None = None) -> float:
    m = ACTIONS.match(name)
    if not m:
        raise ValueError(f"no measure {name!r}: ergostat.actions.held (or approved, auto, denied, ran, failed), @CLASS")
    return counts(p, now, m.group(2))[m.group(1)]
