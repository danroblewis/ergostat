"""Corrections the record already holds: ``ergostat corrections scan``. Each is proposed, like any correction,
for the owner to confirm, with the event it came from as its source:

- **a dismissal with a reason**: the owner dismissing a proposed change to the model, a decision or a
  correction (``*.dismissed`` from the owner, with its reason): the reason corrects what made the proposal;
- **an item reopened**: an item moved back to an earlier state of its projection, or by an event named
  ``*.reopened``, with the reason its event gives (``reason``, ``why``, ``note``); one with no reason is not
  a correction anyone can learn from, and is passed by;
- **a message classed as a correction**: an ``ergostat.message`` (the owner's words, SPEC §5a) whose data
  says ``class: correction``, or, unclassed, that the stand-in's heuristics read as one.

Scanning again records nothing new: each correction's id comes from the event it rests on."""

from __future__ import annotations

from ..spec.items import project
from . import acts, standin
from .kinds import CORRECTION, DECISION
from .transcript import Turn

REASONS = ("dismissed_reason", "dismissed_because", "reason", "why", "note")
WORK = {"ergostat.model-change": "modelling", DECISION: "decision extraction", CORRECTION: "correction extraction"}


def _reason(data: dict) -> str:
    return next((str(data[k]).strip() for k in REASONS if isinstance(data.get(k), str) and data[k].strip()), "")


def _when(e: dict) -> dict:
    from .transcript import iso
    return {"time": iso(e["time"]), "event": e["id"]}


def found(p, spec=None) -> list[dict]:
    """What the record says, as proposals (not yet recorded)."""
    out: list[dict] = []
    for e in p.events.query(n=None, source=acts.OWNER):
        r = _reason(e.get("data") or {}) if e["type"].endswith(".dismissed") else ""
        if not r:
            continue
        kind = (e["item"] or "").split("/", 1)[0]
        what = e["type"].rsplit(".", 1)[0]
        out.append({"item": f"{CORRECTION}/from-{e['id'][:12]}", "data": {
            "correction": r[:acts.TEXT_MAX], "words": [{"text": r, **_when(e)}],
            "corrects": f"what proposed {e['item']}", "kind_of_work": [WORK.get(kind, what)], "scope": [kind or what],
            "source": {"type": "dismissal", "event": e["id"], "item": e["item"]}}})
    if spec is not None and getattr(spec, "items", None):
        moved = set()
        for it in project(p.events, spec):
            k = spec.items.get(it.kind or "")
            if not k or not k.states or it.kind in (CORRECTION, DECISION):
                continue
            for m in it.moves:
                back = m["from"] in k.states and m["to"] in k.states and k.states.index(m["to"]) < k.states.index(m["from"])
                if not (back or m["type"].endswith(".reopened")):
                    continue
                if m["event"] in moved:             # (a move two projections of one id both make: one correction)
                    continue
                e = p.events.get(m["event"]) or {}
                r = _reason(e.get("data") or {})
                if not r:
                    continue
                moved.add(m["event"])
                out.append({"item": f"{CORRECTION}/from-{m['event'][:12]}", "data": {
                    "correction": r[:acts.TEXT_MAX], "words": [{"text": r, **_when(e)}],
                    "corrects": f"{it.id} taken as {m['from']} when it was not", "kind_of_work": [it.kind or "general"],
                    "scope": [it.kind] if it.kind else [], "source": {"type": "reopened", "event": e["id"], "item": it.id}}})
    for e in p.events.query(n=None, type="ergostat.message,ergostat.message.received"):   # the owner's messages (SPEC §12h)
        d = e.get("data") or {}
        text = str(d.get("text") or d.get("message") or "").strip()
        cls = d.get("class")
        if not text or cls not in (None, "correction"):
            continue
        if cls is None:
            t = Turn("owner", text, 0, e["time"], str(d.get("session") or "message"))
            hits = [x for k, x in standin.read(t, "earlier work", "") if k == "correction"]
            if not hits:
                continue
            sentence = hits[0]["correction"]
        else:
            sentence = text.split("\n", 1)[0][:acts.TEXT_MAX]
        work = d.get("kind_of_work") or standin.topics(text) or ["general"]
        about = d.get("about")
        about = ", ".join(map(str, about)) if isinstance(about, list) else about
        out.append({"item": f"{CORRECTION}/from-{e['id'][:12]}", "data": {
            "correction": sentence, "words": [{"text": text, **_when(e)}], "corrects": str(about or e.get("item") or ""),
            "kind_of_work": work, "scope": standin.topics(text),
            "source": {"type": "message", "event": e["id"], **({"item": e["item"]} if e.get("item") else {})}}})
    return out


def scan(p, spec=None, source: str = "ergostat") -> dict:
    got = {"proposed": 0, "known": 0, "repeats": 0, "items": []}
    for x in found(p, spec):
        r = acts.propose(p, CORRECTION, x["data"], source, item=x["item"])
        got["known" if r["status"] == "known" else "proposed"] += 1
        got["repeats"] += 1 if r.get("repeats") else 0
        got["items"].append(r["item"])
    return got
