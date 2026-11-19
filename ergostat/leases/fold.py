"""A lease folded onto its item (SPEC §9.5), from the events, so the fold is the truth: whatever ergostat was doing
when it stopped, the item says who holds it, until when, how many attempts it has had and how each went.

The item's field ``lease`` (ergostat's own: an event's data never replaces it):

    {"fence": 3, "holder": RUN, "block": "developer", "tier": "ai", "ttl": 2400, "taken": T, "renewed": T,
     "expires": T, "back": "ready", "attempts": 1, "max": 3, "not_before": T, "dead": T,
     "history": [{"fence", "run", "block", "taken", "renewed", "ended", "how", "why", "exit", "counted"}, ...]}

``holder`` is None while nobody holds it. The events (``ergostat.lease.*``, ergostat's own, about the item):

- ``taken`` (run, block, fence, ttl, max, back, tier): the item moves to ``leased``. Refused while it is held, when the
  fence is not the next one, or when it is a dead letter;
- ``renewed`` (run, fence): explicit; any event the holder caused about the item renews it too, and so does a line of
  its transcript (``claude.*``);
- ``ended`` (run, fence, how ``ack`` or ``nack``, why, exit, after, count, news): ack, the work moved the item on (it
  stays where the work moved it); nack, given back: to ``back``, its attempt counted unless ``count`` is false, and not
  taken again before ``after`` seconds, or, with ``news``, before the first event about it its own runs did not cause
  (a webhook's: the review it waits for);
- ``expired`` (run, fence, silent): silent past its TTL: to ``back``, its attempt counted;
- ``redriven`` (to, why): a dead letter given another go: to ``to`` (else ``back``), its attempts from nothing.

A counted attempt that reaches ``max`` moves the item to ``dead`` instead. An event about the item caused by a run
whose lease on it ended is refused, whatever it says: the fencing number travelled with the run, and is past."""

from __future__ import annotations

from ..spec.ir import DEAD, LEASED
from . import ENDED, EXPIRED, PREFIX, REDRIVEN, RENEWED, TAKEN


def is_lease(e: dict) -> bool:
    return e["type"].startswith(PREFIX)


def held(fields: dict) -> dict | None:
    """The lease held on an item, or None."""
    lease = fields.get("lease")
    return lease if isinstance(lease, dict) and lease.get("holder") else None


def _summary(lease: dict) -> dict:
    return {k: lease.get(k) for k in ("fence", "holder", "block", "expires", "attempts") if lease.get(k) is not None}


def apply(it, e: dict, kind, history: bool = False) -> tuple[str | None, str | None]:
    """A lease event folded onto the item: the state it moves the item to (None: it stays), and why it was refused
    (None: it applied)."""
    d = e.get("data") or {}
    t, now = e["type"], e["time"]
    cur = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else {}
    lease = {**cur, "history": [dict(h) for h in cur.get("history") or []]}
    to = None
    if t == TAKEN:
        if cur.get("holder"):
            return None, f"already leased to run {str(cur['holder'])[:8]} (fence {cur.get('fence')}): one lease at a time"
        if it.state == DEAD:
            return None, "a dead letter: redrive it before it is taken again"
        want = int(cur.get("fence") or 0) + 1
        if d.get("fence") != want:
            return None, f"fence {d.get('fence')} is not the next one ({want})"
        ttl = float(d.get("ttl") or 0)
        lease.update({"fence": want, "holder": d.get("run"), "block": d.get("block"), "tier": d.get("tier"), "ttl": ttl,
                      "taken": now, "renewed": now, "expires": now + ttl, "back": d.get("back") or it.state,
                      "max": int(d.get("max") or 1), "attempts": int(cur.get("attempts") or 0)})
        lease.pop("not_before", None)
        lease.pop("news", None)
        lease.pop("woken", None)
        lease["history"].append({"fence": want, "run": d.get("run"), "block": d.get("block"), "taken": now})
        to = LEASED
    elif t == REDRIVEN:
        if it.state != DEAD:
            return None, f"only a dead letter is redriven (it is {it.state or 'in no state'})"
        lease["attempts"] = 0
        lease.pop("dead", None)
        lease.pop("not_before", None)
        states = kind.states if kind else []
        to = d.get("to") if d.get("to") in states else lease.get("back") or (states[0] if states else None)
    elif t in (RENEWED, ENDED, EXPIRED):
        if not cur.get("holder") or d.get("fence") != cur.get("fence") or (d.get("run") and d.get("run") != cur.get("holder")):
            last = next((h for h in reversed(cur.get("history") or []) if h.get("fence") == d.get("fence")), None)
            return None, (f"lease {d.get('fence')} is not held: it ended ({last.get('how')})" if last and last.get("how")
                          else f"lease {d.get('fence')} is not the one held ({cur.get('fence') or 'none'})")
        if t == RENEWED:
            lease["renewed"] = max(now, float(cur.get("renewed") or 0))
            lease["expires"] = lease["renewed"] + float(cur.get("ttl") or 0)
        else:
            how = "expired" if t == EXPIRED else ("ack" if d.get("how") == "ack" else "nack")
            counted = how == "expired" or (how == "nack" and d.get("count", True) is not False)
            last = lease["history"][-1] if lease["history"] else {}
            last.update({"ended": now, "how": how, "renewed": cur.get("renewed"), "counted": counted,
                         **{k: d[k] for k in ("why", "exit", "note", "silent") if d.get(k) is not None}})
            lease["holder"] = None
            lease.pop("expires", None)
            if how == "ack":
                lease["attempts"] = 0
                to = lease.get("back") if it.state == LEASED else None   # acked unmoved (by hand): back where it was
            else:
                lease["attempts"] = int(cur.get("attempts") or 0) + (1 if counted else 0)
                if d.get("after"):
                    lease["not_before"] = now + float(d["after"])
                    if d.get("news"):                       # or sooner: at the first news of it (``news``)
                        lease["news"] = True
                if lease["attempts"] >= int(cur.get("max") or 1):
                    lease["dead"] = now
                    last["dead"] = True
                    to = DEAD
                else:
                    to = lease.get("back")
    else:
        return None, f"{t}: not a lease event ergostat knows"
    it.fields["lease"] = lease
    if history:
        it.changes.append({"time": now, "event": e["id"], "type": t, "form": "lease", "op": t.rsplit(".", 1)[1],
                           "path": "/lease", "before": _summary(cur) or None, "after": _summary(lease)})
    return to, None


def fenced(it, e: dict) -> str | None:
    """Why an event about the item is refused by fencing: it was caused by a run whose lease on it has ended."""
    run = e.get("causedby")
    lease = it.fields.get("lease")
    if not run or not isinstance(lease, dict) or run == lease.get("holder"):
        return None
    h = next((x for x in lease.get("history") or [] if x.get("run") == run), None)
    if h is None or not h.get("ended"):
        return None
    return (f"from run {run[:8]}, whose lease on it (fence {h.get('fence')}) ended ({h.get('how')}); the lease now is "
            f"{lease.get('fence')}: refused, not applied (fencing)")


def news(it, e: dict) -> None:
    """An item given back to wait for news (a nack with ``news``) is ready again at the first event about it that its
    own runs did not cause and that is not ergostat's: a webhook's, a person's, another block's."""
    lease = it.fields.get("lease")
    if not isinstance(lease, dict) or not lease.get("news") or lease.get("holder") or not lease.get("not_before"):
        return
    if e["type"].startswith(("ergostat.", "agent.")):
        return
    ran = {h.get("run") for h in lease.get("history") or []}
    if e.get("causedby") and e["causedby"] in ran:
        return
    lease.pop("not_before", None)
    lease.pop("news", None)
    lease["woken"] = e["time"]


def renew(it, e: dict) -> None:
    """Any event the holder caused about the item, or a line of its transcript, renews its lease."""
    lease = held(it.fields)
    if lease is None or e["time"] < float(lease.get("renewed") or 0):
        return
    if e.get("causedby") == lease["holder"] or e["type"].startswith("claude."):
        lease["renewed"] = e["time"]
        lease["expires"] = e["time"] + float(lease.get("ttl") or 0)
