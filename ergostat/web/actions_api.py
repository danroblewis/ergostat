"""Gated actions on the page (SPEC §12k): ``GET /api/actions`` (the latest, or those about one item, with the counts
per class) and ``POST /api/action/ID/approve`` or ``/deny`` (``note=``: why), the owner's answer to one held."""

from __future__ import annotations

KEEP = ("id", "state", "action", "class", "gate", "args", "command", "in", "item", "branch", "block", "session", "time",
        "approved_by", "denied_by", "note", "exit", "output", "deliveries")


def listing(p, item: str | None = None) -> dict:
    from ..actions import record
    got = record.about(p, item) if item else sorted(record.stored(p).values(), key=lambda a: -a["time"])
    return {"actions": [{k: a.get(k) for k in KEEP} for a in got[:100]], "classes": record.by_class(p),
            "counts": record.counts(p)}


def post(live, path: str, q: dict) -> tuple[int, dict]:
    from ..actions import gate
    p = live.get()
    spec = getattr(p.model, "spec", None)
    if spec is None:
        return 400, {"error": "the model is an ergostat.toml: gated actions are an ergostat.yaml's"}
    from urllib.parse import unquote
    aid, _, verb = unquote(path.removeprefix("action/")).rpartition("/")   # action/ID/approve (the ID has a / in it)
    if not aid or verb not in ("approve", "deny"):
        return 400, {"error": "POST /api/action/ID/approve or /api/action/ID/deny"}
    note = (q.get("note") or [None])[0]
    try:
        if verb == "approve":
            a = gate.approve(p, spec, aid, by="owner", note=note)
        else:
            a = gate.deny(p, aid, by="owner", note=note)
    except gate.GateError as e:
        return 400, {"error": str(e)}
    return 200, {k: a.get(k) for k in KEEP}
