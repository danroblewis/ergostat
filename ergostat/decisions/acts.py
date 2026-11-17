"""Proposing a decision or a correction, and the owner's acts on one. Every step is an event about the item, so
the item, folded from them, is the decision (``ergostat.decision/<slug>``) or the correction
(``ergostat.correction/<slug>``); nothing is kept anywhere else.

A proposal is checked before it is recorded (``check_proposal``): its sentence, the owner's words it rests on
(verbatim, each with where it came from: the session, the line, the time), and the rest of its fields in their
shapes. The same check serves a block's event line, ``ergostat decisions propose`` and the MCP ``record_event``.

The owner's acts each need what makes them meaningful: a dismissal, a supersession and a retirement need a
reason; a supersession also names the decision that replaces it, and is never implied by another decision
saying it supersedes this one. A correction that says what an earlier one said is linked to that first one
(``repeats``) and the first records ``ergostat.correction.repeated``: a repeat is the finding that the first
did not change what was done (``spec/watch.py``)."""

from __future__ import annotations

import hashlib
import time

from ..spec.items import Item, fold
from .kinds import CORRECTION, DECISION, KINDS, OWNERS, PROPOSED, builtin, item_id, kind_of_id, words_of

OWNER = "owner"
TEXT_MAX = 400            # a decision or correction is one sentence; more is a paragraph, and refused
QUOTE_MAX = 20000         # one quote of the owner's words, at most (a pasted document is pointed at, not kept)
SIMILAR = 0.5             # the share of content words two corrections share to be the same point (Jaccard)
CONTAINED = 0.75          # or the share of the shorter's words found in the longer


class ActError(ValueError):
    pass


# ---- reading

def items(p, kind: str, until: float | None = None) -> list[Item]:
    """Every decision (or correction) as it stands, the newest first."""
    k = builtin()[kind]
    by: dict[str, list[dict]] = {}
    for e in p.events.of_items([k.id], until=until):
        by.setdefault(e["item"], []).append(e)
    return sorted((fold(i, evs, k) for i, evs in by.items()), key=lambda i: -i.last)


def one(p, id: str) -> Item | None:
    kind = kind_of_id(id)
    if kind is None:
        return None
    evs = p.events.query(n=None, item=id)
    return fold(id, evs, builtin()[kind]) if evs else None


def full_id(kind: str, id: str) -> str:
    """An id as given: whole (``ergostat.decision/x-1a2b``) or its slug alone (``x-1a2b``)."""
    return id if id.startswith(f"{kind}/") else f"{kind}/{id}"


# ---- a proposal, checked

def _list(v, what: str) -> list:
    if v is None:
        return []
    if isinstance(v, (str, dict)):
        return [v]
    if isinstance(v, list):
        return v
    raise ActError(f"{what}: a list")


def _words(raw, what: str = "words") -> list[dict]:
    out = []
    for w in _list(raw, what):
        if isinstance(w, str):
            w = {"text": w}
        if not isinstance(w, dict) or not isinstance(w.get("text"), str) or not w["text"].strip():
            raise ActError(f"{what}: each the owner's words verbatim, {{\"text\", \"session\", \"line\", \"time\"}}")
        q = {"text": w["text"][:QUOTE_MAX]}
        if len(w["text"]) > QUOTE_MAX:
            q["cut"] = len(w["text"])
        for k in ("session", "file", "speaker"):
            if w.get(k) is not None:
                q[k] = str(w[k])
        if w.get("line") is not None:
            try:
                q["line"] = int(w["line"])
            except (TypeError, ValueError):
                raise ActError(f"{what}.line: a line number") from None
        if w.get("time") is not None:
            q["time"] = w["time"] if isinstance(w["time"], (int, float)) else str(w["time"])
        out.append(q)
    return out


def _sentence(v, what: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ActError(f"{what}: one sentence, required")
    v = " ".join(v.split())
    if len(v) > TEXT_MAX:
        raise ActError(f"{what}: one sentence ({len(v)} characters; at most {TEXT_MAX})")
    return v


def _strings(v, what: str) -> list[str]:
    out = []
    for x in _list(v, what):
        if not isinstance(x, (str, int, float)) or not str(x).strip():
            raise ActError(f"{what}: a list of words or phrases")
        out.append(" ".join(str(x).split()))
    return out


def check_proposal(kind: str, data: dict, source: str) -> dict:
    """The proposal's fields as recorded, or ``ActError`` saying what is wrong."""
    if not isinstance(data, dict):
        raise ActError("a proposal's data is an object")
    text_key = "decision" if kind == DECISION else "correction"
    out: dict = {text_key: _sentence(data.get(text_key), text_key)}
    words = _words(data.get("words"))
    if not words:
        if source != OWNER:
            raise ActError("words: the owner's words it rests on, verbatim, with where they came from; required")
        words = [{"text": out[text_key], "speaker": OWNER}]       # the owner proposing: their sentence is their words
    out["words"] = words
    out["scope"] = _strings(data.get("scope"), "scope")
    if kind == DECISION:
        out["reasons"] = _strings(data.get("reasons"), "reasons")
        alts = []
        for a in _list(data.get("alternatives"), "alternatives"):
            if isinstance(a, str):
                a = {"option": a}
            if not isinstance(a, dict) or not str(a.get("option") or "").strip():
                raise ActError("alternatives: each {\"option\", \"why\"}: what was rejected, and why")
            alts.append({"option": " ".join(str(a["option"]).split()), "why": " ".join(str(a.get("why") or "").split())})
        out["alternatives"] = alts
        sup = _strings(data.get("supersedes"), "supersedes")
        out["supersedes"] = [full_id(DECISION, s) for s in sup]
    else:
        out["corrects"] = " ".join(str(data.get("corrects") or "").split())
        out["kind_of_work"] = _strings(data.get("kind_of_work"), "kind_of_work") or ["general"]
        if data.get("repeats"):
            out["repeats"] = full_id(CORRECTION, str(data["repeats"]))
        src = data.get("source")
        if src is not None and not isinstance(src, dict):
            raise ActError("source: an object ({\"type\": \"transcript|dismissal|reopened|message\", \"event\": ID})")
        if src:
            out["source"] = src
    if data.get("confidence") is not None:
        c = data["confidence"]
        c = {"low": 0.3, "medium": 0.6, "high": 0.9}.get(c, c)
        try:
            out["confidence"] = max(0.0, min(1.0, float(c)))
        except (TypeError, ValueError):
            raise ActError("confidence: 0 to 1, or low, medium, high") from None
    if data.get("extractor"):
        out["extractor"] = data["extractor"] if isinstance(data["extractor"], dict) else {"name": str(data["extractor"])}
    out["proposed_by"] = str(data.get("proposed_by") or source)
    return out


def _eid(*parts) -> str:
    return hashlib.sha1("\n".join(str(x) for x in parts).encode()).hexdigest()[:32]


def _stem(w: str) -> str:
    """A word's plain form, roughly: ``pages`` and ``page``, ``adding`` and ``add``, are one word here."""
    for end in ("ing", "s"):
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[: -len(end)]
    return w


def similar(a: str, b: str) -> bool:
    """Two corrections make the same point: most of their content words are shared."""
    from .kinds import STOP
    x = {_stem(w) for w in words_of(a) if w not in STOP and len(w) > 2}
    y = {_stem(w) for w in words_of(b) if w not in STOP and len(w) > 2}
    if len(x) < 2 or len(y) < 2:
        return False
    both = len(x & y)
    return both / len(x | y) >= SIMILAR or both / min(len(x), len(y)) >= CONTAINED


def first_like(p, data: dict, before: list[Item] | None = None) -> Item | None:
    """The first correction, not dismissed, that the proposed one repeats."""
    kinds = set(data.get("kind_of_work") or [])
    text = str(data.get("correction") or "")         # the owner's point, not what it corrected (the assistant's words)
    olds = [i for i in (before if before is not None else items(p, CORRECTION)) if i.state != "dismissed"]
    for i in sorted(olds, key=lambda i: i.first):
        f = i.fields
        if f.get("repeats"):
            continue
        theirs = set(f.get("kind_of_work") or [])
        if kinds and theirs and not (kinds & theirs) and "general" not in kinds | theirs:
            continue
        if similar(text, str(f.get("correction") or "")):
            return i
    return None


def propose(p, kind: str, data: dict, source: str, item: str | None = None, causedby: str | None = None,
            at: float | None = None) -> dict:
    """Record a proposal: ``{"status": "proposed" | "known", "item", "event"}``, or ``ActError``. The same
    proposal again (the same item) records nothing new."""
    if kind not in KINDS:
        raise ActError(f"{kind}: not a kind of intent ({', '.join(KINDS)})")
    d = check_proposal(kind, data, source)
    text = d["decision" if kind == DECISION else "correction"]
    id = full_id(kind, item) if item else item_id(kind, text)
    if kind_of_id(id) != kind or not id.split("/", 1)[1]:
        raise ActError(f"item: {kind}/<slug>")
    had = one(p, id)
    if had is not None:                                     # seen again: its new words, if any, are added to it
        known = {" ".join(str(w.get("text", "")).split()) for w in had.fields.get("words") or []}
        fresh = [w for w in d["words"] if " ".join(w["text"].split()) not in known]
        if not fresh or had.state == "dismissed":
            return {"status": "known", "item": id, "state": had.state}
        seen = {"by": source, **{k: d[k] for k in ("confidence", "extractor") if k in d}}
        ev = p.events.add(f"{kind}.seen", item=id, source=source, causedby=causedby, at=at,
                          id=_eid(id, "seen", *(w["text"] for w in fresh)), data={"words": fresh, "evidence": [seen]})
        return {"status": "known", "item": id, "state": had.state, "added_words": len(fresh), "event": ev["id"]}
    if kind == DECISION:
        for s in d["supersedes"]:
            if one(p, s) is None:
                raise ActError(f"supersedes: no decision {s}")
    first = None
    if kind == CORRECTION:
        if d.get("repeats"):
            first = one(p, d["repeats"])
            if first is None:
                raise ActError(f"repeats: no correction {d['repeats']}")
            if first.fields.get("repeats"):                     # always linked to the first of them
                d["repeats"] = first.fields["repeats"]
                first = one(p, d["repeats"])
        else:
            first = first_like(p, d)
            if first is not None:
                d["repeats"] = first.id
    ev = p.events.add(f"{kind}.proposed", item=id, source=source, causedby=causedby, data=d, at=at,
                      id=_eid(id, "proposed"))
    if first is not None:
        n = 1 + sum(1 for i in items(p, CORRECTION) if i.fields.get("repeats") == first.id and i.id != id)
        p.events.add(f"{CORRECTION}.repeated", item=first.id, source="ergostat", causedby=ev["id"], at=at,
                     id=_eid(first.id, "repeated", id),
                     data={"repeated_n": n, "repeated_by": [{"item": id, "text": d["words"][0]["text"][:500],
                                                              **{k: v for k, v in d["words"][0].items() if k != "text"}}]})
    return {"status": "proposed", "item": id, "event": ev["id"], **({"repeats": first.id} if first else {})}


# ---- the owner's acts

def _need(p, kind: str, id: str, states: tuple[str, ...], act: str) -> Item:
    id = full_id(kind, id)
    it = one(p, id)
    if it is None:
        raise ActError(f"no {kind} {id}")
    if it.state not in states:
        raise ActError(f"{id} is {it.state}: only a {' or '.join(states)} one can be {act}")
    return it


def _reason(reason, act: str, required: bool) -> str | None:
    r = " ".join(str(reason or "").split()) or None
    if required and not r:
        raise ActError(f"{act} needs a reason: it is what the next proposal learns from")
    return r


def confirm(p, kind: str, id: str, reason: str | None = None, by: str = OWNER) -> dict:
    it = _need(p, kind, id, ("proposed",), "confirmed")
    r = _reason(reason, "confirming", False)
    ev = p.events.add(f"{kind}.confirmed", item=it.id, source=by, data={"confirmed_by": by, **({"confirmed_reason": r} if r else {})})
    return {"item": it.id, "state": "confirmed", "event": ev["id"]}


def dismiss(p, kind: str, id: str, reason: str | None, by: str = OWNER) -> dict:
    it = _need(p, kind, id, ("proposed",), "dismissed")
    r = _reason(reason, "dismissing", True)
    ev = p.events.add(f"{kind}.dismissed", item=it.id, source=by, data={"dismissed_by": by, "dismissed_reason": r})
    return {"item": it.id, "state": "dismissed", "event": ev["id"]}


def supersede(p, id: str, by_decision: str, reason: str | None, by: str = OWNER) -> dict:
    """A confirmed decision replaced by another, explicitly: the reason and the decision that replaces it."""
    it = _need(p, DECISION, id, ("confirmed",), "superseded")
    r = _reason(reason, "superseding", True)
    if not by_decision:
        raise ActError("superseding needs the decision that replaces it")
    new = one(p, full_id(DECISION, by_decision))
    if new is None:
        raise ActError(f"no decision {full_id(DECISION, by_decision)} to replace it")
    if new.id == it.id or new.state in ("dismissed", "superseded"):
        raise ActError(f"{new.id} is {new.state if new.id != it.id else 'this one'}: it cannot replace it")
    ev = p.events.add(f"{DECISION}.superseded", item=it.id, source=by,
                      data={"superseded_by": new.id, "superseded_reason": r, "superseded_by_who": by})
    sup = sorted(set(new.fields.get("supersedes") or []) | {it.id})
    p.events.add(f"{DECISION}.supersedes", item=new.id, source=by, causedby=ev["id"], data={"supersedes": sup})
    return {"item": it.id, "state": "superseded", "by": new.id, "event": ev["id"]}


def retire(p, id: str, reason: str | None, by: str = OWNER) -> dict:
    """A confirmed correction that no longer applies (the behaviour it corrected is gone)."""
    it = _need(p, CORRECTION, id, ("confirmed",), "retired")
    r = _reason(reason, "retiring", True)
    ev = p.events.add(f"{CORRECTION}.retired", item=it.id, source=by, data={"retired_by": by, "retired_reason": r})
    return {"item": it.id, "state": "retired", "event": ev["id"]}


# ---- an event line from a block (or the MCP record_event)

def take_line(p, type: str, item: str | None, data: dict, source: str, causedby: str | None = None) -> dict:
    """A block's ``{"event": "ergostat.decision.proposed", ...}``: the one kind of ``ergostat.`` event a block
    may print, checked like any proposal. The owner's acts are refused: a block proposes, the owner decides."""
    if type in OWNERS:
        raise ActError(f"{type}: the owner's act, not a block's (a block proposes)")
    if type not in PROPOSED:
        raise ActError(f"{type}: ergostat's own")
    kind = type.rsplit(".", 1)[0]
    return propose(p, kind, data or {}, source, item=item, causedby=causedby)


def now() -> float:
    return time.time()
