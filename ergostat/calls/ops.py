"""What each call to the engine's socket does (``server.py``), with the engine's own record and model: the same as the
command it stands for, answered as that command's ``--json`` answers.

- ``event``: ``{"events": [...]}``, the envelope of ``POST /api/events`` (``intake/envelope.py``); ``causedby`` the
  run asking. Answers what was recorded and, for an event that changed its item by a patch, a set or a fold rule, why
  the fold refused it (``unchanged``), as ``event --add`` says it;
- ``act``: ``{"name", "args", "key", "wait", "env"}``: ``ergostat act``, the run's ``ERGOSTAT_ACTIONS`` from ``env``;
  a call that has to wait for an answer is parked (``server.py``);
- ``lease``: ``{"how": "renew" | "nack", "why", "after", "count", "env"}``: ``ergostat lease --renew`` / ``--nack``;
- ``item``: ``{"id"}``: ``ergostat item ID --json``;
- ``items``: ``{"kind", "state", "offset"}``: ``ergostat item --kind K --state S --json`` (each optional), so a daemon
  reads the items without starting a process: a page of them from ``offset``, and ``total``, how many match;
- ``ping``: whether it listens, and for which project."""

from __future__ import annotations


class Refused(Exception):
    def __init__(self, why: str, code: int = 2):
        super().__init__(why)
        self.code = code


def call_of(req: dict) -> str | None:
    """The call's own key (``client.call``), the same on every try: what it records is named by it."""
    k = req.get("call")
    return f"call-{k}"[:72] if isinstance(k, str) and k else None


def act_key(cfg: dict, req: dict) -> str | None:
    """An act's key: the caller's, else this call's for a run with no item (one with finds its act by its arguments)."""
    key = req.get("key")
    return call_of(req) if key is None and not cfg.get("item") else key


def event(eng, req: dict) -> dict:
    from ..intake import envelope
    from ..spec import items as its
    from ..spec.triggers import block_of, undeclared
    why = undeclared(eng.spec, block_of(eng.p.events, req.get("causedby")),   # the run's block, from its record
                     [e.get("event") for e in req.get("events") or [] if isinstance(e, dict)])
    if why:                                              # a run started by events says only what it declares (SPEC §9.3)
        raise Refused(f"not recorded: {why}")
    try:
        evs = envelope.parse(req.get("events"))
        if call_of(req):                                 # asked again after a restart: recorded once (by its id)
            evs = [{**e, "id": e.get("id") or f"{call_of(req)}.{i}"} for i, e in enumerate(evs)]
        got = envelope.record(eng.p, evs, source=str(req.get("source") or "user"), causedby=req.get("causedby") or None)
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


def items(eng, req: dict) -> dict:
    from ..spec import items as its
    return its.listing(eng.p.events, eng.spec, kind=req.get("kind") or None, state=req.get("state") or None,
                       offset=max(0, int(req.get("offset") or 0)))


def lease(eng, req: dict) -> dict:
    from ..leases import acts
    env = req.get("env") or {}
    try:
        if req.get("how") == "renew":
            return {"event": acts.renew(eng.p, eng.spec, env=env, id=call_of(req))}
        if req.get("how") == "nack":
            return {"event": acts.nack(eng.p, eng.spec, str(req.get("why") or "given back"), after=req.get("after"),
                                       count=req.get("count", True) is not False, env=env, id=call_of(req))}
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
        return program.start(eng.p, eng.spec, cfg, str(req.get("name") or ""), args, key=act_key(cfg, req)), cfg
    except program.AskError as e:
        raise Refused(f"refused: {e}") from None


def act_answer(eng, cfg: dict, a: dict) -> dict:
    from ..actions import gate, program
    a = program.finish(eng.p, cfg, a)
    return {"action": gate.result(a), "full": a, "exit": program.exit_code(a)}
