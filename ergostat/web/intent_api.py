"""The owner's answers to a proposed decision or correction, from its item's page (``POST /api/intent/ACT?id=ID``,
with ``reason``, and ``by``, the decision that replaces it, for a supersede): ``confirm``, ``dismiss``,
``supersede`` (a decision) and ``retire`` (a correction). Each is the owner's own act, recorded as an event about
the item (``decisions/acts.py``), and none changes the model."""

from __future__ import annotations

from ..decisions import acts
from ..decisions.kinds import CORRECTION, DECISION, kind_of_id

ACTS = {DECISION: ("confirm", "dismiss", "supersede"), CORRECTION: ("confirm", "dismiss", "retire")}


def post(live, path: str, q: dict) -> tuple[int, dict]:
    parts = path.strip("/").split("/")
    first = lambda k: ((q.get(k) or [""])[0] or "").strip() or None    # noqa: E731
    id = first("id")
    kind = kind_of_id(id or "")
    if len(parts) != 2 or parts[0] != "intent" or kind is None or parts[1] not in ACTS[kind]:
        return 404, {"error": "not found: POST /api/intent/ACT?id=ergostat.decision/... (or ergostat.correction/...)"}
    p = live.get()
    act, reason = parts[1], first("reason")
    try:
        if act == "confirm":
            got = acts.confirm(p, kind, id, reason)
        elif act == "dismiss":
            got = acts.dismiss(p, kind, id, reason)
        elif act == "supersede":
            got = acts.supersede(p, id, first("by") or "", reason)
        else:
            got = acts.retire(p, id, reason)
    except acts.ActError as e:
        return 409, {"error": str(e)}
    return 200, got
