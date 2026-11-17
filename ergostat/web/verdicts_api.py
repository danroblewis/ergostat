"""The intent judge on the page (SPEC §12i): ``GET /api/verdicts`` (the counts and rates by kind, the latest verdicts),
and the owner's acts, ``POST /api/verdict/overrule?id=ID&reason=R`` (a verdict was wrong) and ``POST
/api/verdict/reopen?item=ITEM&reason=R`` (work accepted that was not done as meant goes back). Each is the owner's
own act, recorded as an event (``intent/record.py``); neither changes the model."""

from __future__ import annotations

from ..intent import measures, record


def table(p, snap) -> dict | None:
    spec = getattr(p.model, "spec", None)
    if spec is None:
        return None
    t = measures.table(p, spec, now=snap["at"])
    return {k: t[k] for k in ("since", "until", "all", "kinds", "held")}


def post(live, path: str, q: dict) -> tuple[int, dict]:
    first = lambda k: ((q.get(k) or [""])[0] or "").strip() or None    # noqa: E731
    act = path.strip("/").removeprefix("verdict/")
    p = live.get()
    spec = getattr(p.model, "spec", None)
    if spec is None or act not in ("overrule", "reopen"):
        return 404, {"error": "not found: POST /api/verdict/overrule?id=... or /api/verdict/reopen?item=..."}
    try:
        if act == "overrule":
            got = record.overrule(p, first("id") or "", first("reason"))
            return 200, {"id": got["id"], "state": "overruled", "work": got["work"]}
        ev = record.reopen(p, spec, first("item") or "", first("reason"))
        return 200, {"item": ev["item"], "reopened": ev["data"]["reopened"]}
    except record.VerdictError as e:
        return 400, {"error": str(e)}
