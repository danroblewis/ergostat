"""The owner's messages on the page (SPEC §12h): ``POST /api/message`` (the text in the body, as JSON ``{"text",
"about"}``; or ``route=ID&about=X``, routing one by hand) and ``GET /api/messages`` (the latest, or those about one
item, with the counts)."""

from __future__ import annotations

import json


def post(live, q: dict, body: bytes) -> tuple[int, dict]:
    from ..messages import record, route
    p = live.get()
    spec = getattr(p.model, "spec", None)
    if spec is None:
        return 400, {"error": "the model is an ergostat.toml: messages are routed to the work of an ergostat.yaml"}
    try:
        got = json.loads(body.decode() or "{}") if body else {}
    except ValueError:
        return 400, {"error": "the body: JSON, {\"text\": \"...\", \"about\": \"review/2041\"}"}
    if not isinstance(got, dict):
        return 400, {"error": "the body: a JSON object"}
    about = got.get("about") or (q.get("about") or [None])[0]
    try:
        if got.get("route") or q.get("route"):          # one routed by hand: an unrouted message, or again
            mid = str(got.get("route") or q["route"][0])
            if not about:
                return 400, {"error": "route a message to something: about (an item, or a part)"}
            return 200, route.route(p, spec, mid, about=about, by="owner")
        text = got.get("text") or (q.get("text") or [""])[0]
        return 200, route.send(p, spec, str(text), by="owner", about=about or None, via="page")
    except record.MessageError as e:
        return 400, {"error": str(e)}


def listing(p, item: str | None = None) -> dict:
    from ..messages import measures, record
    ms = sorted(record.stored(p).values(), key=lambda m: -m["time"])
    if item:
        ms = [m for m in ms if item in (m.get("about") or []) or any(t.get("item") == item for t in m.get("routed_to") or [])
              or any(d.get("item") == item or d.get("follow_up") == item for d in m.get("deliveries") or [])]
    keep = ("id", "state", "text", "by", "sent", "time", "matched", "why", "routed_to", "deliveries", "answers", "outcome",
            "missed", "queued", "about")
    return {"messages": [{k: m.get(k) for k in keep} for m in ms[:100]], "counts": measures.counts(p)}
