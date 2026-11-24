"""The forecast (``numbers/forecast.py``, ``forecast/v1``: each open item's completion estimate, each kind's, group's
and stage's), for the Items page, the Timeline, an item's page, ``/api/forecast``, the SQL source's ``forecast_*``
views and the remote API (SPEC §5a, *Completion estimates*, *The forecast*; ``numbers/eta.py``). Worked out by one
worker thread, never on a request: a request is given what was last worked out (None the first time) and asks for
the next when the record changed since, at most every ``EVERY`` seconds (and every ``KEPT`` seconds whatever: a
lease's age moves with the clock). A record changed only where the simulation does not read it (its fingerprint,
``forecast.fingerprint``: every input but what moves with the clock alone, unchanged) keeps the last answer and its
version, unrun, within ``KEPT`` of when it was computed. The worker works out one
at a time, the latest asked for first (an older ask for another what-if waits, and is dropped when a newer one for the
same comes). The owner's what-if (a block's ``pool`` or ``failure``) is kept apart; the eight used last are kept.
How well last week's estimates held (``numbers/etacheck.py``: each kind's calibration) is worked out by the same
worker when no estimate waits, at most once an ``HOUR`` for the kinds asked, and given beside the estimates."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

EVERY = 30.0
KEPT = 120.0
KEEP = 8
HOUR = 3600.0
_CACHE: OrderedDict = OrderedDict()       # key → {"made", "mark", "ans"}, the least used first
_WANT: OrderedDict = OrderedDict()        # key → its work, the latest asked last
_CAL: OrderedDict = OrderedDict()         # (spec, kinds) → {"made" (when begun), "ans"}, the oldest first
_CAL_WANT: OrderedDict = OrderedDict()    # (spec, kinds) → (p, spec, kinds): worked out when no estimate waits
_LOCK = threading.Condition()
_WORKER: list = []
_SERIAL = [0]                             # the last forecast version given out (numbers/forecast.py: ``version``)


def kinds_of(spec) -> list[str]:
    return [k for k, ik in (getattr(spec, "items", None) or {}).items() if ik.states and not k.startswith("ergostat.")]


def estimates(p, m, whatif: str | None = None, wait: float = 0.0) -> dict | None:
    """The latest estimates (``{"at", "runs", "items": {id: {p50, p90, start, why, ...}}, "kinds", "schedule",
    "capacity", "calibration"}``), or None while the first is worked out; ``wait``: seconds to wait for it (tests)."""
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
    ckey = (id(spec), tuple(kinds))
    until = time.monotonic() + wait
    with _LOCK:
        cal = _CAL.get(ckey)
        if (cal is None or time.time() - cal["made"] >= HOUR) and ckey not in _CAL_WANT:
            _CAL_WANT[ckey] = (p, spec, kinds)
            while len(_CAL_WANT) > KEEP:
                _CAL_WANT.popitem(last=False)
        while True:
            got = _CACHE.get(key)
            if got is not None:
                _CACHE.move_to_end(key)
            age = time.time() - got["made"] if got else None
            if got is None or (got["mark"] != mark and age >= EVERY) or age >= KEPT:
                _WANT.pop(key, None)
                _WANT[key] = (p, spec, kinds, mark, w)
            if (_WANT or _CAL_WANT) and (not _WORKER or not _WORKER[0].is_alive()):
                _WORKER[:] = [threading.Thread(target=_worker, daemon=True, name="eta")]
                _WORKER[0].start()
            _LOCK.notify_all()
            left = until - time.monotonic()
            if got is not None or left <= 0:
                ans, cal = got["ans"] if got else None, (_CAL.get(ckey) or {}).get("ans")
                return {**ans, "calibration": cal} if ans and cal else ans
            _LOCK.wait(min(left, 0.1))


def current(p, m) -> dict | None:
    """The forecast as another reader asks it (``/api/forecast``, the SQL views, the remote API): as ``estimates``,
    and for a model with no kind to forecast, a forecast saying so (never None, which is 'being worked out')."""
    if not kinds_of(getattr(m, "spec", None)):
        from ..numbers.forecast import failed
        return failed("this model has no item kind with states: nothing to forecast", time.time(), None, error=False)
    return estimates(p, m)


def _worker() -> None:
    while True:
        with _LOCK:
            while not _WANT and not _CAL_WANT:
                if not _LOCK.wait(60.0):
                    _WORKER.clear()                    # idle a minute: gone, started again when asked
                    return
            if not _WANT:                              # no estimate waits: last week's held against what happened
                ckey, (p, spec, kinds) = _CAL_WANT.popitem(last=False)
                old = _CAL.pop(ckey, None)             # (stamped when begun: asked again an hour after)
                _CAL[ckey] = {"made": time.time(), "ans": old["ans"] if old else None}
                while len(_CAL) > KEEP:
                    _CAL.popitem(last=False)
            else:
                ckey, (key, (p, spec, kinds, mark, w)) = None, _WANT.popitem(last=True)
                kept = _CACHE.get(key)
        if ckey is not None:
            cal = _calibrate(p, spec, kinds)
            with _LOCK:
                if cal is not None and ckey in _CAL:
                    _CAL[ckey]["ans"] = cal
                _LOCK.notify_all()
            continue
        ans, fp = _work(p, spec, kinds, w, mark, kept)
        with _LOCK:                                    # (a failure kept too: said, tried again as an answer is)
            if kept is None or ans is not kept["ans"]:   # (worked out again: a new version, one counter for all)
                _SERIAL[0] += 1
                ans = {**ans, "version": _SERIAL[0]}
            _CACHE[key] = {"made": time.time(), "mark": mark, "ans": ans, "fp": fp}
            _CACHE.move_to_end(key)
            while len(_CACHE) > KEEP:
                _CACHE.popitem(last=False)
            _LOCK.notify_all()


def _calibrate(p, spec, kinds) -> dict | None:
    from ..numbers import etacheck
    try:
        return etacheck.calibration(p, spec, kinds, time.time())
    except Exception as e:                       # the Timeline says nothing of it; said in the server's log
        import sys
        print(f"eta calibration: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _work(p, spec, kinds, w, mark=(None,), old: dict | None = None) -> tuple[dict, str | None]:
    """The forecast (``numbers/forecast.py``) and what it read (its fingerprint): ``old``'s answer again, unrun, when
    what the simulation reads of the record is unchanged and it was computed within ``KEPT``."""
    from ..numbers import eta, etamodel, forecast
    try:
        inp = etamodel.read(p, spec, kinds, time.time())
        fp = forecast.fingerprint(inp, w.pools, w.failures)
        if old and old.get("fp") == fp and time.time() - (old["ans"].get("computed") or 0.0) < KEPT:
            return old["ans"], fp
        sets, left = forecast.sets(inp)
        sim = eta.simulate(inp, pools=w.pools, failures=w.failures, sets=sets)
        why = eta.reasons(inp, w.pools)
        sources = {b.name: _source(b, w.pools, getattr(spec.blocks.get(b.name), "pool_now", None)) for b in inp.blocks}
        return forecast.build(inp, sim, why, time.time(), mark[0], w.said(), sources, left), fp
    except Exception as e:                       # the page goes on without estimates, the failure said on it and in the log
        import sys
        print(f"eta: {type(e).__name__}: {e}", file=sys.stderr)
        return forecast.failed(f"{type(e).__name__}: {e}", time.time(), mark[0]), None


def _source(b, pools: dict, now) -> str:
    """Where a block's simulated capacity comes from, in words: what binds (seats, a daemon), the what-if, its pool."""
    bind = next((n for n, c in b.shared if c < pools.get(b.name, b.pool)), None)
    if bind:
        return f"{bind.split(':', 1)[1]}'s {'seats' if bind.startswith('agent') else 'runs at once'}"
    if b.name in pools:
        return "what if"
    return f"pool {now} now" if now else "pool"


def merge(ans: dict, est: dict | None) -> dict:
    """The Graph's and Timeline's answer (``precedence.build``) with the forecast (``est``: ``forecast/v1``, as
    ``estimates`` gives it; numbers/forecast.py): each open item's p50, p90 and why
    (an item left out of the run: unscheduled, and why, with no bar ahead), its projected bars from the levelled run (a
    block's lane on each), each kind's last finish, each block's capacity and where it comes from, and each kind's
    calibration (how well last week's estimates held: ``{coverage, items, mae, since, said}``, ``{}`` until worked
    out); a failed simulation's error as ``eta_error``."""
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
    return {**ans, "items": items, "eta": {"schema": est.get("schema"), "version": est.get("version"),
                                           "computed": est.get("computed"), "at": est["at"], "runs": est["runs"],
                                           "kinds": est["kinds"],
                                           "capacity": est["capacity"], "sources": est.get("sources") or {},
                                           "limit": est.get("limit") or {}, "assumed": est.get("assumed") or {},
                                           "whatif": est.get("whatif") or [],
                                           "calibration": est.get("calibration") or {}}}
