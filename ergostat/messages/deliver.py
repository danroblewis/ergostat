"""Delivering a message to the work it was routed to (SPEC §12h).

- **A running session** (a block run whose session the helper ``ergostat session`` started): the helper takes the
  messages routed to its run, its session or the items its run works on (``for_session``), and gives each to the
  session as its next turn; ``delivered``, how ``live`` (written into the running session) or ``resume`` (``claude -p
  --resume`` after its turn, the message as its input).
- **A block that is no session**, or one not running now: its next run's context carries the messages routed to it,
  or to open items of the kinds it works on (``for_context``), under ``messages``; ``delivered``, how ``context``.
- **Finished work** (``finished``): by the model's ``messages: {finished:}`` policy, a **follow-up** (a new item
  linked to it, in its kind's first state, so the work that does that kind takes it up), a **reopening** (the item
  moves back, ``ergostat.item.reopened``), or **attention** (unrouted, for the owner). When the message was received
  before the work finished, the work finished without it: **missed** (work redone because a message did not reach it).

``sweep`` runs on ergostat's clock: it routes messages left received, and applies the finished policy to messages whose
items all finished while they waited to be delivered (missed)."""

from __future__ import annotations

import fnmatch
import hashlib
import time

from ..spec.ir import Block, Spec
from ..spec.items import REOPENED
from . import record, route

FOLLOW_UP = "ergostat.item.follow-up"
SWEEP_AFTER = 5.0             # a message left received this long (ergostat stopped between recording and routing it)


def delivered(p, msg: dict, how: str, *, run: str | None = None, session: str | None = None, block: str | None = None,
              item: str | None = None, by: str = "ergostat", **more) -> dict:
    d = {"how": how, "at": time.time(), **({"run": run} if run else {}), **({"session": session} if session else {}),
         **({"block": block} if block else {}), **({"item": item} if item else {}), **more}
    to = session or (f"block {block}" if block else None) or item or "the work"
    words = {"live": f"delivered to {to}, live", "resume": f"delivered to {to}, as its next turn (resumed)",
             "context": f"delivered to {to}, in its run's context", "follow-up": f"a follow-up of {item}: {more.get('follow_up')}",
             "reopen": f"reopened {item}"}
    return record.step(p, msg["id"], "delivered", {"deliveries": d, "outcome": words.get(how, f"delivered ({how})")},
                       by=by, causedby=run)


def queued(p, msg: dict, *, session: str, run: str | None, why: str, by: str = "ergostat") -> dict:
    return record.step(p, msg["id"], "queued", {"queued": {"session": session, "run": run, "why": why, "at": time.time()},
                                                "outcome": f"queued for {session}'s next step: {why}"}, by=by, causedby=run)


def answered(p, mid: str, says: str, *, by: str, run: str | None = None, session: str | None = None) -> dict:
    msg = record.get(p, mid)
    if msg is None:
        raise record.MessageError(f"no message {mid!r}")
    says = str(says or "").strip()[:2000]
    if not says:
        raise record.MessageError("an answer says something: {\"answer\": {\"message\": ID, \"says\": \"...\"}}")
    return record.step(p, msg["id"], "answered", {"answers": {"says": says, "by": by, "at": time.time(),
                                                              **({"run": run} if run else {}),
                                                              **({"session": session} if session else {})},
                                                  "outcome": f"answered by {session or by}"}, by=by, causedby=run)


def awaiting(p, since: float | None = None) -> list[dict]:
    """Messages routed and not yet delivered."""
    return [m for m in record.stored(p, since=since).values() if m["state"] == "routed"]


def _brief(m: dict) -> dict:
    return {"id": m["id"], "text": m.get("text"), "by": m.get("by"), "sent": m.get("sent"), "about": m.get("about") or [],
            "items": sorted({t["item"] for t in m.get("routed_to") or [] if t.get("item")}),
            "matched": m.get("matched")}


def note(m: dict) -> str:
    """A message as a session reads it, its next turn."""
    b = _brief(m)
    about = f" (about {', '.join(b['items'] or b['about'])})" if b["items"] or b["about"] else ""
    return (f"A message from {b['by']}{about}, sent while you work ({record.short(m['id'])}):\n\n{b['text']}\n\n"
            f"Take it into the work you are doing. To answer it, print the JSON line "
            f"{{\"answer\": {{\"message\": \"{m['id']}\", \"says\": \"...\"}}}} among your last lines.")


# ---- to a running session

def for_session(p, spec: Spec, run: str | None, session: str | None = None) -> list[dict]:
    """The messages awaiting delivery that are this run's or this session's: routed to it, or to an item it works on
    now, or to its block while it runs."""
    if not run and not session:
        return []
    mine = set()
    block = None
    if run:
        start = p.events.get(run)
        block = start.get("item") if start else None
        for e in p.events.caused_by(run):
            i = e.get("item") or ""
            if "/" in i and not i.startswith("ergostat.") and not (e.get("data") or {}).get("session_id"):
                mine.add(i)
    out = []
    for m in awaiting(p, since=time.time() - route.RUN_FOR):
        for t in m.get("routed_to") or []:
            if t.get("finished"):
                continue
            if (run and t.get("run") == run) or (session and t.get("session") == session) or \
                    (not t.get("run") and t.get("item") in mine) or (not t.get("run") and block and t.get("block") == block):
                out.append(m)
                break
    return out


# ---- in a run's context

def kinds_worked(spec: Spec, b: Block) -> set[str]:
    """The kinds of item a block works on: those counted by the sensors of the flows it sets, the stocks they move,
    and what the goals it serves are about."""
    parts = []
    for t in b.targets():
        if t.kind == "flow" and t.name in spec.flows:
            f = spec.flows[t.name]
            parts.append(f)
            parts += [spec.stocks[s] for s in (f.source, f.target) if s in spec.stocks]
    goals = {r.name for r in b.reads() if r.kind == "goal"} | ({b.goal} if b.goal else set())
    for g in goals:
        if g in spec.goals:
            of = spec.goals[g].of
            x = spec.measured(of.kind).get(of.name)
            if x is not None:
                parts.append(x)
    out = {b.takes.kind} if getattr(b, "takes", None) else set()   # the kind it takes (SPEC §9.5)
    for x in parts:
        for s in getattr(x, "sensors", {}).values():
            if s.items and s.items.get("kind"):
                out.add(str(s.items["kind"]))
    return out


def for_context(p, spec: Spec, b: Block, run: str, item: str | None = None) -> list[dict]:
    """The messages awaiting delivery that this run of ``b`` is given in its context (``messages``): routed to the
    block, or to open items of a kind it works on (a run on a leased ``item``: to that item only), and not to a run
    going now; each recorded delivered (``context``)."""
    waiting = awaiting(p, since=time.time() - 7 * 86400)
    if not waiting:
        return []
    kinds = kinds_worked(spec, b)
    live = {r["run"] for r in route.running(p, spec)} - {run}
    out = []
    for m in waiting:
        for t in m.get("routed_to") or []:
            if t.get("run") in live or t.get("finished"):
                continue
            item_kind = route_kind(spec, t.get("item"))
            if t.get("block") == b.name or (t.get("item") and not t.get("block") and item_kind in kinds
                                            and (item is None or t.get("item") == item)):
                delivered(p, m, "context", run=run, block=b.name, item=t.get("item"))
                out.append(_brief(m))
                break
    return out


def route_kind(spec: Spec, item: str | None) -> str | None:
    if not item:
        return None
    from ..spec.items import kind_of
    k = kind_of(spec, item)
    return k.name if k else None


# ---- finished work

def _follow_up_id(p, spec: Spec, kind_name: str, item: str, mid: str) -> str | None:
    k = spec.items[kind_name]
    if kind_name == route_kind(spec, item):           # its own kind: review/2041 → review/2041.1, .2, ...
        n = 1 + sum(1 for x in p.events.items() if x["item"].startswith(item + "."))
        cand = f"{item}.{n}"
        if k.matches(cand):
            return cand
    h = hashlib.sha1(f"{item}\n{mid}".encode()).hexdigest()[:8]
    cand = k.id.replace("**", "*").replace("*", h, 1).replace("*", "").replace("?", "x")
    return cand if fnmatch.fnmatchcase(cand, k.id) else None


def finished(p, spec: Spec, msg: dict, it: dict, by: str = "ergostat", policy: str | None = None) -> dict:
    """A message about an item already finished, by the policy: follow-up, reopen, or attention. Missed, too, when the
    message was received before the item finished (it waited, and the work went on without it)."""
    policy = policy or spec.messages.finished
    missed = (msg.get("sent") or msg["time"]) < (it.get("entered") or 0)
    text = msg.get("text") or ""
    cause = msg.get("received_event")
    if missed:
        record.step(p, msg["id"], "missed", {"missed": {"item": it["id"], "state": it["state"], "finished": it["entered"],
                                                        "policy": policy},
                                             "outcome": f"missed: {it['id']} finished ({it['state']}) before it was delivered"},
                    by=by, causedby=cause)
    if policy == "reopen":
        k = spec.items[it["kind"]]
        to = spec.messages.reopen_to.get(it["kind"]) or (k.states[0] if k.states else None)
        p.events.add(REOPENED, item=it["id"], source=by, causedby=cause,
                     data={"reopened": {"to": to, "message": msg["id"], "says": text[:500], "missed": missed,
                                        "from": it["state"], "at": time.time()}})
        return delivered(p, msg, "reopen", item=it["id"], by=by, to=to, missed=missed)
    if policy == "follow-up":
        kind = spec.messages.follow_up or it["kind"]
        new = _follow_up_id(p, spec, kind, it["id"], msg["id"])
        if new is not None:
            k = spec.items[kind]
            keep = {f: it["fields"][f] for f in [*k.show, "title"] if f in it["fields"] and kind == it["kind"]
                    and not str(it["fields"][f]).startswith("file:")}
            p.events.add(FOLLOW_UP, item=new, source=by, causedby=cause,
                         data={**keep, "follows": it["id"], "message": msg["id"], "note": text[:2000], "missed": missed,
                               "done_when": text[:2000]})      # the owner's words, verbatim: what it is judged by (§12i)
            return delivered(p, msg, "follow-up", item=it["id"], by=by, follow_up=new, missed=missed)
        why = f"about {it['id']}, finished ({it['state']}); no id of kind {kind} could be made for a follow-up"
    else:
        why = f"about {it['id']}, finished ({it['state']}): messages: {{finished: attention}} leaves it to the owner"
    return record.step(p, msg["id"], "unrouted", {"matched": msg.get("matched") or "explicit", "routed_to": [], "why": why,
                                                  "outcome": f"unrouted: {why}"}, by=by)


def sweep(p, spec: Spec, now: float | None = None) -> int:
    """Route what was left received; apply the finished policy to messages whose items all finished before any work
    took them (missed). Returns how many it moved."""
    now = time.time() if now is None else now
    msgs = record.stored(p, since=now - 7 * 86400)
    n = 0
    for m in msgs.values():
        if m["state"] == "received" and now - m["time"] >= SWEEP_AFTER:
            route.route(p, spec, m["id"])
            n += 1
    waiting = [m for m in msgs.values() if m["state"] == "routed"]
    if not waiting:
        return n
    runs = {r["run"] for r in route.running(p, spec, now)}
    items = None
    for m in waiting:
        to = [t for t in m.get("routed_to") or [] if not t.get("finished")]
        if not to or any(t.get("run") in runs for t in to) or any(not t.get("item") for t in to):
            continue
        if items is None:
            items = {x["id"]: x for x in route.work_items(p, spec)}
        its = [items.get(t["item"]) for t in to]
        if all(x is not None and x["finished"] for x in its):
            for x in {x["id"]: x for x in its}.values():
                finished(p, spec, m, x)
            n += 1
    return n
