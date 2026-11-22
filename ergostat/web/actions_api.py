"""Gated actions on the page (SPEC §12k): ``GET /api/actions`` (the latest, or those about one item, with the counts
per class) and ``POST /api/action/ID/approve`` or ``/deny`` (``note=``: why), the owner's answer to one held. The inbox
(SPEC §12o): ``GET /api/inbox`` and ``POST /api/inbox/ID/approve``, ``/deny`` or ``/done`` (``n=``), any kind."""

from __future__ import annotations

from ..webaccess import who

KEEP = ("id", "state", "action", "class", "gate", "args", "command", "in", "item", "branch", "block", "session", "time",
        "approved_by", "denied_by", "note", "exit", "output", "deliveries")


def listing(p, item: str | None = None, classes: bool = False) -> dict:
    from ..actions import record
    if classes:                                   # the Items page's line per class: asked, approved, denied, held
        return {"asked": record.asked(p, getattr(p.model, "spec", None))}
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
            a = gate.approve(p, spec, aid, by=who(), note=note)
        else:
            a = gate.deny(p, aid, by=who(), note=note)
    except gate.GateError as e:
        return 400, {"error": str(e)}
    return 200, {k: a.get(k) for k in KEEP}


def inbox(p) -> dict:
    from ..inbox import stats
    spec = getattr(p.model, "spec", None)
    return {"entries": stats.listing(p, spec), "classes": stats.by_class(p, spec)} if spec is not None else {"entries": []}


def answer(live, path: str, q: dict) -> tuple[int, dict]:
    from urllib.parse import unquote

    from ..inbox.answer import AnswerError
    from ..inbox.answer import answer as give
    p = live.get()
    eid, _, verb = unquote(path.removeprefix("inbox/")).rpartition("/")
    one = lambda k: (q.get(k) or [None])[0]               # noqa: E731
    try:
        n = float(one("n")) if one("n") not in (None, "") else None
        return 200, give(p, p.model.spec, eid, verb, n, one("note"), by=who())
    except (AnswerError, ValueError, AttributeError) as e:
        return 400, {"error": str(e)}
