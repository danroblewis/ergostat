"""``POST /api/events`` and ``POST /api/hooks/NAME``: events pushed to the running ergostat (``intake/``), recorded
and folded at once. Answers: 200 with what was recorded; 202 when a hook's payload made no event (a sender's event
the mapping leaves out); 400 a push refused whole (nothing of it recorded); 401 without the token; 403 from an address
``intake: allow:`` does not name; 404 a hook not in the model; 413 too large."""

from __future__ import annotations

import json


def post(live, path: str, q: dict, headers, address: str, body: bytes | None, size: int) -> tuple[int, dict]:
    from ..intake import envelope, hooks
    from ..intake.token import allowed, carried, token
    p = live.get()
    spec = getattr(p.model, "spec", None)
    cfg = getattr(spec, "intake", None)
    if not allowed(address, getattr(cfg, "allow", None) or []):
        return 403, {"error": f"{address} may not push (intake: allow: names who may, besides this machine)"}
    if body is None:
        return (413, {"error": f"{size} bytes: too large"}) if size else (400, {"error": "nothing was sent"})
    if not carried(token(p.dir), headers, q, body):
        return 401, {"error": f"the token is missing or wrong (it is in {p.dir / 'intake.token'})"}
    try:
        if path == "/api/events":
            got = envelope.record(p, envelope.parse(body), source="push")
            return 200, got
        name = path.removeprefix("/api/hooks/").strip("/")
        hook = (getattr(cfg, "hooks", None) or {}).get(name)
        if hook is None:
            return 404, {"error": f"no hook {name!r} (intake: hooks: in the model names them)"}
        try:
            payload = json.loads(body or b"null")
        except ValueError as e:
            return 400, {"error": f"not JSON ({e})"}
        evs, left = hooks.events(hook, payload, headers)
        if not evs:
            return 202, {"recorded": 0, "ignored": left}
        got = envelope.record(p, evs, source=name)
        return 200, {**got, **({"ignored": left} if left else {})}
    except envelope.Refused as e:
        return 400, {"error": str(e)}
