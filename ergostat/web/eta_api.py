"""Each open item's completion estimate, for the Items page, the Timeline and an item's page (SPEC §5a, *Completion
estimates*; ``numbers/eta.py``). Worked out by one worker thread, never on a page's request: a request is given what
was last worked out (None the first time) and asks for the next when the record changed since, at most every
``EVERY`` seconds (and every ``KEPT`` seconds whatever: a lease's age moves with the clock). The worker works out one
at a time, the latest asked for first (an older ask for another what-if waits, and is dropped when a newer one for the
same comes). The owner's what-if (a block's ``pool`` or ``failure``) is kept apart; the eight used last are kept."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

EVERY = 30.0
KEPT = 120.0
KEEP = 8
_CACHE: OrderedDict = OrderedDict()       # key → {"made", "mark", "ans"}, the least used first
_WANT: OrderedDict = OrderedDict()        # key → its work, the latest asked last
_LOCK = threading.Condition()
_WORKER: list = []


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
    with _LOCK:
        while True:
            got = _CACHE.get(key)
            if got is not None:
                _CACHE.move_to_end(key)
            age = time.time() - got["made"] if got else None
            if got is None or (got["mark"] != mark and age >= EVERY) or age >= KEPT:
                _WANT.pop(key, None)
                _WANT[key] = (p, spec, kinds, mark, w)
                if not _WORKER or not _WORKER[0].is_alive():
                    _WORKER[:] = [threading.Thread(target=_worker, daemon=True, name="eta")]
                    _WORKER[0].start()
                _LOCK.notify_all()
            left = until - time.monotonic()
            if got is not None or left <= 0:
                return got["ans"] if got else None
            _LOCK.wait(min(left, 0.1))


def _worker() -> None:
    while True:
        with _LOCK:
            while not _WANT:
                if not _LOCK.wait(60.0):
                    _WORKER.clear()                    # idle a minute: gone, started again when asked
                    return
            key, (p, spec, kinds, mark, w) = _WANT.popitem(last=True)
        ans = _work(p, spec, kinds, w)
        with _LOCK:                                    # (a failure kept too: said, tried again as an answer is)
            _CACHE[key] = {"made": time.time(), "mark": mark, "ans": ans}
            _CACHE.move_to_end(key)
            while len(_CACHE) > KEEP:
                _CACHE.popitem(last=False)
            _LOCK.notify_all()


def _work(p, spec, kinds, w) -> dict:
    from ..numbers import eta, etamodel
    try:
        inp = etamodel.read(p, spec, kinds, time.time())
        ans = eta.simulate(inp, pools=w.pools, failures=w.failures)
        why = eta.reasons(inp, w.pools)
        for i, x in ans["items"].items():               # (reasons' words kept; one not scheduled says so first)
            r = dict(why.get(i) or {})
            if x.get("unscheduled"):                    # (the bare reason kept for the Timeline row and item page)
                r["said"] = x["why"]
            if x.get("unscheduled") and not r.get("why", "").startswith(x["why"]):
                r["why"] = f"not scheduled: {x['why']}" + (f"; {r['why']}" if r.get("why") else "")
            elif x.get("out"):                          # (counted out in some runs: said after reasons' words)
                r["why"] = "; ".join(filter(None, [r.get("why"), x["why"]]))
            x.update(r)
        ans["assumed"] = {b.name: b.assumed for b in inp.blocks if b.assumed}
        ans["sources"] = {b.name: _source(b, w.pools, getattr(spec.blocks.get(b.name), "pool_now", None))
                          for b in inp.blocks}
        ans["whatif"] = w.said()
        return ans
    except Exception as e:                       # the page goes on without estimates, the failure said on it and in the log
        import sys
        print(f"eta: {type(e).__name__}: {e}", file=sys.stderr)
        return {"error": f"{type(e).__name__}: {e}", "items": {}, "kinds": {}}


def _source(b, pools: dict, now) -> str:
    """Where a block's simulated capacity comes from, in words: what binds (seats, a daemon), the what-if, its pool."""
    bind = next((n for n, c in b.shared if c < pools.get(b.name, b.pool)), None)
    if bind:
        return f"{bind.split(':', 1)[1]}'s {'seats' if bind.startswith('agent') else 'runs at once'}"
    if b.name in pools:
        return "what if"
    return f"pool {now} now" if now else "pool"


def merge(ans: dict, est: dict | None) -> dict:
    """The Graph's and Timeline's answer (``precedence.build``) with the estimates: each open item's p50, p90 and why
    (an item left out of the run: unscheduled, and why, with no bar ahead), its projected bars from the levelled run (a
    block's lane on each), each kind's last finish, and each block's capacity and where it comes from; a failed
    simulation's error as ``eta_error``."""
    if not est or not est.get("items"):
        return {**ans, "eta": None, "eta_error": (est or {}).get("error")}
    items = []
    for x in ans["items"]:
        e = est["items"].get(x["id"])
        if e is not None:
            x = {**x, "eta": e}
            segs = est["schedule"].get(x["id"])
            if e.get("unscheduled"):                 # (no bar ahead: the forward pass's dropped too)
                x["projected"] = []
            elif segs:
                x["projected"] = [s for s in segs if s[2] > est["at"]]
        items.append(x)
    return {**ans, "items": items, "eta": {"at": est["at"], "runs": est["runs"], "kinds": est["kinds"],
                                           "capacity": est["capacity"], "sources": est.get("sources") or {},
                                           "limit": est.get("limit") or {}, "assumed": est.get("assumed") or {},
                                           "whatif": est.get("whatif") or []}}
