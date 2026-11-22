"""The Items page's Graph and Timeline (SPEC §5a, *Relations*; ``precedence.py``): the items of the kinds asked, the
items their relations reach, each one's status, the critical path and the schedule.

``GET /api/items-graph?kinds=ticket,epic`` (or ``system=NAME``: the system's kinds; with both, the kinds asked, and
only the system's own dependency network: another system's items are stubs, ``precedence.build(own=)``). The answer is worked out when
the record changes, and kept until it does again (or for ``KEPT`` seconds at most): a page left open on a quiet
record is given the same answer, and draws nothing new; its projections are from the moment it was worked out
(``now`` in it)."""

from __future__ import annotations

import threading
import time

KEPT = 300.0              # an answer is worked out again at least this often, the record quiet or not
_CACHE: dict = {}
_LOCK = threading.Lock()


def kinds_asked(spec, q: dict) -> list[str]:
    from .. import process as pm
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    asked = [k for k in (one("kinds") or "").split(",") if k in spec.items]
    return asked or pm.kinds_of(spec, one("system") or None)


def graph(p, m, snap: dict, q: dict) -> dict:
    from .. import precedence
    spec = getattr(m, "spec", None)
    if spec is None or not getattr(spec, "items", None):
        return {"now": snap["at"], "since": snap["at"] - snap["window"], "kinds": [], "items": [], "edges": [],
                "cycles": [], "critical": [], "end": snap["at"], "capped": {}, "assumed": None}
    kinds = kinds_asked(spec, q)
    from .. import process as pm
    system = (q.get("system") or [None])[0] or None
    own = pm.kinds_of(spec, system) if system else None          # a system's Graph: its own dependency network
    ev = p.events
    seq = ev.last_seq() if hasattr(ev, "last_seq") else None
    gen = ev.generation() if hasattr(ev, "generation") else None
    live = abs(time.time() - snap["at"]) < 5                    # now, not a moment travelled to
    key = (id(spec), tuple(kinds), system, seq, gen, snap["window"], live or snap["at"])
    with _LOCK:
        got = _CACHE.get(key)
        if got is not None and time.time() - got[0] < KEPT:
            return got[1]
    now = snap["at"]
    ans = precedence.build(ev, spec, kinds, now, now - snap["window"], until=None if live else now,   # as it stood then
                           own=own)
    ans["asked"] = kinds
    with _LOCK:
        for k in [k for k in _CACHE if k[:3] == key[:3] or time.time() - _CACHE[k][0] > KEPT]:
            _CACHE.pop(k, None)
        _CACHE[key] = (time.time(), ans)
        while len(_CACHE) > 32:
            _CACHE.pop(next(iter(_CACHE)))
    return ans
