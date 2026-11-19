"""What each call to the engine's socket does (``server.py``), with the engine's own record and model: the same as the
command it stands for, answered as that command's ``--json`` answers.

- ``event``: ``{"events": [...]}``, the envelope of ``POST /api/events`` (``intake/envelope.py``); ``causedby`` the
  run asking. Answers what was recorded and, for an event that changed its item by a patch, a set or a fold rule, why
  the fold refused it (``unchanged``), as ``event --add`` says it;
- ``act``: ``{"name", "args", "key", "wait", "env"}``: ``ergostat act``, the run's ``ERGOSTAT_ACTIONS`` from ``env``;
  a call that has to wait for an answer is parked (``server.py``);
- ``lease``: ``{"how": "renew" | "nack", "why", "after", "count", "env"}``: ``ergostat lease --renew`` / ``--nack``;
- ``item``: ``{"id"}``: ``ergostat item ID --json``;
- ``ping``: whether it listens, and for which project."""

from __future__ import annotations


class Refused(Exception):
    def __init__(self, why: str, code: int = 2):
        super().__init__(why)
        self.code = code


def event(eng, req: dict) -> dict:
    from ..intake import envelope
    from ..spec import items as its
    try:
        got = envelope.record(eng.p, envelope.parse(req.get("events")), source=str(req.get("source") or "user"),
                              causedby=req.get("causedby") or None)
    except envelope.Refused as e:
        raise Refused(f"not recorded: {e}") from None
    spec = eng.spec
    unchanged = {}
    for e, eid in zip(req.get("events") or [], got["ids"], strict=False):
        item = e.get("item")
        if not (isinstance(item, str) and "/" in item):
            continue
        if e.get("patch") is None and e.get("set") is None and not getattr(its.kind_of(spec, item), "fold", None):
            continue
        it = its.one(eng.p.events, spec, item)
        why = next((r["why"] for r in (it.refused if it else []) if r["event"] == eid), None)
        if why:
            unchanged[eid] = why
    return {**got, **({"unchanged": unchanged} if unchanged else {})}


def item(eng, req: dict) -> dict:
    from ..spec import items as its
    d = its.detail(eng.p.events, eng.spec, str(req.get("id") or ""), history=its.HISTORY_SHOWN)
    if d is None:
        raise Refused(f"no item {req.get('id')!r}")
    return {"item": d}


def lease(eng, req: dict) -> dict:
    from ..leases import acts
    env = req.get("env") or {}
    try:
        if req.get("how") == "renew":
            return {"event": acts.renew(eng.p, eng.spec, env=env)}
        if req.get("how") == "nack":
            return {"event": acts.nack(eng.p, eng.spec, str(req.get("why") or "given back"), after=req.get("after"),
                                       count=req.get("count", True) is not False, env=env)}
    except acts.LeaseError as e:
        raise Refused(f"refused: {e}", 1) from None
    raise Refused(f"lease: how is renew or nack, not {req.get('how')!r}")


def act_start(eng, req: dict) -> tuple[dict, dict]:
    """The action asked for, and the run's actions file it was asked under (``program.given``)."""
    from ..actions import program
    try:
        cfg = program.given(req.get("env") or {})
        args = req.get("args") or {}
        if not isinstance(args, dict):
            raise program.AskError("args: a map of NAME to VALUE")
        return program.start(eng.p, eng.spec, cfg, str(req.get("name") or ""), args, key=req.get("key")), cfg
    except program.AskError as e:
        raise Refused(f"refused: {e}") from None


def act_answer(eng, cfg: dict, a: dict) -> dict:
    from ..actions import gate, program
    a = program.finish(eng.p, cfg, a)
    return {"action": gate.result(a), "full": a, "exit": program.exit_code(a)}
