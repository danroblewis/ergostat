"""The inbox's history (SPEC §12o): each thing asked of a person kept as an item of the built-in projection
``ergostat.inbox``, its key the entry's id (``ergostat.inbox/change/ca4c2e9f``). Written where the inbox is worked out
(``entries.entries``), on a change only: ``ergostat.inbox.asked`` when an entry first appears; when one waiting is gone,
how it was answered, read from the record of its kind (``approved``, ``denied`` or ``done``, by whoever answered: the
inbox, the page, the MCP, a kind's own command, the repair loop's approvers), else ``superseded`` (it stopped being
asked unanswered). ``answer.answer`` writes the answer itself too, with its note and amount. Each event's id is made
from the entry's id and its round (how many times it has been asked), so two writers write it once: an entry asked
once is asked once, and its ending is the first written. What was answered before this was kept is not written back."""

from __future__ import annotations

import hashlib
import time

from ..spec.ir import INBOX

ASKED = ("class", "kind", "summary", "why", "link")
# what its card is drawn from while it waits (the Inbox's list, SPEC §12o): how it is answered and what it says
CARD = ("verbs", "warn", "run", "suggest", "flow", "unit", "block", "system")


def item_of(eid: str) -> str:
    return f"{INBOX}/{eid}"


def _id(eid: str, round: int, what: str) -> str:
    return hashlib.sha1(f"{INBOX}|{eid}|{round}|{what}".encode()).hexdigest()[:32]


def waiting(p, spec) -> dict[str, dict]:
    """The decisions waiting now, by entry id: each one's fields (``round``: which time it is asked)."""
    from ..spec import items as its
    _, _, got = its.in_states(p.events, spec, INBOX, ["waiting"], items=True)
    return {i.id.split("/", 1)[1]: i.fields for i in got}


def asked(p, e: dict, round: int) -> dict | None:
    data = {k: e[k] for k in (*ASKED, *CARD) if e.get(k) not in (None, "", [])}
    data.update(asked=e["time"], round=round, **({"workbench": e["workbench"][0]["link"]} if e.get("workbench") else {}))
    return p.events.add(f"{INBOX}.asked", item=item_of(e["id"]), source="ergostat", data=data,
                        id=_id(e["id"], round, "asked"))


def ended(p, eid: str, round: int, verdict: str, by: str | None = None, note: str | None = None,
          n: float | None = None, at: float | None = None) -> dict:
    """Its answer (``approved``, ``denied``, ``done``) or ``superseded``: the first written of a round is its end."""
    data = {} if verdict == "superseded" else {"answered": at or time.time(), "by": by, "verdict": verdict}
    data.update({"note": note} if note else {}, **({"n": n} if n is not None else {}))
    return p.events.add(f"{INBOX}.{verdict}", item=item_of(eid), source="ergostat" if verdict == "superseded" else (by or "owner"),
                        data=data, id=_id(eid, round, "end"))


def answered(p, spec, eid: str, verb: str, by: str, note: str | None = None, n: float | None = None) -> None:
    """``answer.answer``'s: the entry answered there, with its note and amount (nothing when it was never asked)."""
    from ..spec import items as its
    try:
        it = its.one(p.events, spec, item_of(eid), INBOX)
        if it is not None and it.state == "waiting":
            ended(p, eid, int(it.fields.get("round") or 1), {"approve": "approved", "deny": "denied"}.get(verb, verb),
                  by, note, n)
    except Exception:                                      # the history is not the answer: it never stops one
        pass


def how(p, spec, eid: str) -> tuple | None:
    """How an entry that is no longer waiting was answered, read from its kind's record: (verdict, by, note, n, when),
    or None (no one answered it: it was superseded, expired, or answered of itself)."""
    from ..spec.projections import query
    kind, key = eid.split("/", 1)
    if kind == "action":
        from ..actions import record
        a = record.get(p, key)
        if a is None:
            return None
        to = next((m for m in a.get("moves") or [] if m["to"] in ("approved", "denied")), None)
        by = to and a.get(f"{to['to']}_by")
        if to is None or not by or by == record.GATE:          # (let through, or fenced, by its gate: no one answered)
            return None
        return to["to"], by, a.get("note"), None, to["time"]
    if kind in ("person", "advise", "breaker"):
        block, _, seq = key.rpartition("@")
        b = spec.blocks.get(block)
        if b is None or not seq.isdigit():
            return None
        if kind == "breaker":
            x = query(p, "trigger.reset", n=1, item=block)
            if x and x[0]["seq"] > int(seq):
                return "approved", x[0]["source"], (x[0]["data"] or {}).get("note") or None, None, x[0]["time"]
            return None
        from . import entries as en
        x = next((x for x in en.asks(p, b) if x["seq"] == int(seq)), None)
        if not x or x["answered"] is None or x["verdict"] == "superseded":
            return None
        return ("done" if kind == "person" else x["verdict"]), x.get("by"), x.get("note"), None, x["answered"]
    if kind == "steptest":
        from ..control import proposals as cp
        d = cp.decisions(p).get(key) or {}
        if d.get("status") not in ("approved", "dismissed"):
            return None
        return ("approved" if d["status"] == "approved" else "denied"), d.get("by"), None, None, d.get("decided")
    if kind in ("change", "request"):
        from ..spec.ir import MODEL_CHANGE, MODELLING_REQUEST
        fam = MODEL_CHANGE if kind == "change" else MODELLING_REQUEST
        x = query(p, f"{fam}.*", n=1, item=f"{fam}/{key}")
        if not x:
            return None
        x, what = x[0], x[0]["type"].rsplit(".", 1)[1]
        d = x.get("data") or {}
        if kind == "change" and what in ("accepted", "dismissed"):
            return ("approved" if what == "accepted" else "denied"), x["source"], d.get("dismissed_because"), None, x["time"]
        if kind == "request" and (what == "dismissed" or d.get("approved_by")):
            return ("denied" if what == "dismissed" else "approved"), x["source"], d.get("note"), None, x["time"]
    return None


def sync(p, spec, got: list[dict]) -> int:
    """The decisions made to agree with the entries worked out now: each new one asked, each gone one ended. Returns how
    many events it wrote."""
    if INBOX not in spec.items:
        return 0
    was, now, n = waiting(p, spec), {e["id"]: e for e in got}, 0
    if not was and not now:
        return 0
    from ..spec import items as its
    for eid, e in now.items():
        if eid in was:
            continue
        it = its.one(p.events, spec, item_of(eid), INBOX)
        r = int((it.fields.get("round") or 0) if it is not None else 0) + 1
        n += asked(p, e, r)["seq"] is not None
    for eid, f in was.items():
        if eid in now:
            continue
        try:
            said = how(p, spec, eid)
        except Exception:
            said = None
        verdict, by, note, amount, at = said or ("superseded", None, None, None, None)
        n += ended(p, eid, int(f.get("round") or 1), verdict, by, note, amount, at)["seq"] is not None
    return n
