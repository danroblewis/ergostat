"""Each open item's completion estimate, for the Items page, the Timeline and an item's page (SPEC §5a, *Completion
estimates*; ``numbers/eta.py``). Worked out in a thread of its own, never on a page's request: a request is given what
was last worked out (None the first time) and starts the next when the record changed since, at most every ``EVERY``
seconds (and every ``KEPT`` seconds whatever: a lease's age moves with the clock). The owner's what-if (a block's
``pool`` or ``failure``) is worked out the same way, apart."""

from __future__ import annotations

import threading
import time

EVERY = 30.0
KEPT = 120.0
_CACHE: dict = {}
_BUSY: set = set()
_LOCK = threading.Lock()


def kinds_of(spec) -> list[str]:
    return [k for k, ik in (getattr(spec, "items", None) or {}).items() if ik.states and not k.startswith("ergostat.")]


def estimates(p, m, whatif: str | None = None, wait: float = 0.0) -> dict | None:
    """The latest estimates (``{"at", "runs", "items": {id: {p50, p90, start, why, ...}}, "kinds", "schedule",
    "capacity"}``), or None while the first is worked out; ``wait``: seconds to wait for it (tests)."""
    from ..numbers.closedloop import WhatIfError, parse_whatif
    spec = getattr(m, "spec", None)
    kinds = kinds_of(spec)
    if not kinds:
        return None
    try:
        raw = dict(x.split(":", 1) for x in (whatif or "").split(",") if ":" in x)
        w = parse_whatif(spec, {k: v for k, v in raw.items() if k.startswith("block.")})[1]
    except WhatIfError as e:
        return {"error": str(e), "items": {}, "kinds": {}}
    ev = p.events
    mark = (ev.last_seq(), ev.generation() if hasattr(ev, "generation") else None)
    key = (id(spec), tuple(sorted(w.pools.items())), tuple(sorted(w.failures.items())))
    until = time.monotonic() + wait
    while True:
        with _LOCK:
            got = _CACHE.get(key)
            age = time.time() - got["made"] if got else None
            if key not in _BUSY and (got is None or (got["mark"] != mark and age >= EVERY) or age >= KEPT):
                _BUSY.add(key)
                threading.Thread(target=_work, args=(p, spec, kinds, key, mark, w), daemon=True, name="eta").start()
        if got is not None or time.monotonic() >= until:
            return got["ans"] if got else None
        time.sleep(0.05)


def _work(p, spec, kinds, key, mark, w) -> None:
    from ..numbers import eta, etamodel
    try:
        inp = etamodel.read(p, spec, kinds, time.time())
        ans = eta.simulate(inp, pools=w.pools, failures=w.failures)
        why = eta.reasons(inp, w.pools)
        for i, x in ans["items"].items():
            x.update(why.get(i) or {})
        ans["assumed"] = {b.name: b.assumed for b in inp.blocks if b.assumed}
        ans["whatif"] = w.said()
        with _LOCK:
            _CACHE[key] = {"made": time.time(), "mark": mark, "ans": ans}
            while len(_CACHE) > 8:
                _CACHE.pop(next(iter(_CACHE)))
    except Exception as e:                       # the page goes on without estimates; said in the server's log
        import sys
        print(f"eta: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        with _LOCK:
            _BUSY.discard(key)


def merge(ans: dict, est: dict | None) -> dict:
    """The Graph's and Timeline's answer (``precedence.build``) with the estimates: each open item's p50, p90 and why,
    its projected bars from the levelled run (a block's lane on each), and each kind's last finish."""
    if not est or not est.get("items"):
        return {**ans, "eta": None}
    items = []
    for x in ans["items"]:
        e = est["items"].get(x["id"])
        if e is not None:
            x = {**x, "eta": e}
            segs = est["schedule"].get(x["id"])
            if segs:
                x["projected"] = [s for s in segs if s[2] > est["at"]]
        items.append(x)
    return {**ans, "items": items, "eta": {"at": est["at"], "runs": est["runs"], "kinds": est["kinds"],
                                           "capacity": est["capacity"], "whatif": est.get("whatif") or []}}
