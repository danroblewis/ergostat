"""The classifier a model names (``messages: {classifier: NAME}``, SPEC §12h): a machine block, typically an ``ai``
block on a cheap model, run once for a message no id or name in it routes. It is run like any block (recorded as a
run, ``trigger: message``), given the message and the candidates in its input, and answers with ``route`` lines:

    {"route": {"message": "ergostat.message/1a2b3c", "to": ["review/2041", "block.developer"], "why": "..."}}

``to`` may be empty (it concerns no work). A run that fails, or says nothing about the message, leaves it to the
stand-in."""

from __future__ import annotations

from ..spec.ir import Spec
from . import route

CANDIDATES = 60               # the open items it is shown, those being worked on first, then the newest


def context(spec: Spec, msg: dict, items: list[dict], runs: list[dict]) -> dict:
    busy = {i: r for r in runs for i in r["items"]}
    open_ = [x for x in items if not x["finished"]]
    open_.sort(key=lambda x: (x["id"] not in busy, -x["last"]))
    cands = []
    for x in open_[:CANDIDATES]:
        k = spec.items[x["kind"]]
        cands.append({"id": x["id"], "kind": x["kind"], "state": x["state"],
                      "fields": {f: x["fields"][f] for f in [*k.show, "title"] if f in x["fields"]
                                 and not str(x["fields"][f]).startswith("file:")},
                      **({"worked_on_by": busy[x["id"]]["block"]} if x["id"] in busy else {})})
    blocks = [{"block": b.name, "type": b.type, "description": b.description, "running": any(r["block"] == b.name for r in runs)}
              for b in spec.blocks.values() if b.machine and b.name != spec.messages.classifier]
    return {"message": {"id": msg["id"], "text": msg["text"], "by": msg.get("by"), "sent": msg.get("sent")},
            "candidates": cands, "blocks": blocks,
            "answer": "one line: {\"route\": {\"message\": ID, \"to\": [item ids or block.NAME], \"why\": \"...\"}}; "
                      "an empty to when it concerns none of them"}


def ask(p, spec: Spec, name: str, msg: dict, items: list[dict], runs: list[dict]):
    """(items, parts, how, why), or None when the classifier could not say (the stand-in decides)."""
    from ..spec.engine import Engine
    b = spec.blocks.get(name)
    if b is None:
        return None
    eng = Engine(p, say=lambda s: None)
    try:
        eng.run_block(b, "message", extra=context(spec, msg, items, runs))
    except Exception:
        return None
    got = [r for r in eng.routes.get(b.name, []) if r.get("message") in (msg["id"], route.record.short(msg["id"]))]
    ran = p.events.query(n=1, item=b.name, type="agent.ran,agent.failed")
    if not got or (ran and ran[-1]["type"] == "agent.failed"):
        return None
    its, parts = [], []
    known = {x["id"] for x in items}
    for t in got[-1].get("to") or []:
        t = str(t)
        if t in known or ("/" in t and any(k.matches(t) for k in spec.items.values())):
            its.append(t)
        elif route.part_of(spec, t):
            parts.append(route.part_of(spec, t))
    return its, parts, f"classifier:{b.name}", str(got[-1].get("why") or f"block {b.name} routed it")
