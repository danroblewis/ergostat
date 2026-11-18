"""The remote API (SPEC §4c): what another ergostat reads of this one, under ``/remote/v1/``. Read only (GET),
bounded and paged, behind a bearer token per consumer (``remote/tokens.py``); off (404) until a token is made. The
page's Host check is not applied here, since a tunnel or a proxy sends its own name: the token admits a request."""

from __future__ import annotations

import fnmatch
import threading
import time
from urllib.parse import unquote

EVENTS_MOST = 1000
ITEMS_MOST = 500
READINGS_MOST = 200
POINTS_MOST = 1000
RATE, BURST = 10.0, 30.0             # a token's requests a second, and how many it may make at once

_buckets: dict[str, list[float]] = {}
_lock = threading.Lock()
_served: dict = {}                   # model stamp: the served model (built once per change of the model)


def allowed(who: str) -> float | None:
    """None when ``who`` may ask now; else the seconds to wait (a token bucket per consumer)."""
    now = time.monotonic()
    with _lock:
        tokens, last = _buckets.get(who, [BURST, now])
        tokens = min(BURST, tokens + (now - last) * RATE)
        if tokens < 1.0:
            _buckets[who] = [tokens, now]
            return (1.0 - tokens) / RATE
        _buckets[who] = [tokens - 1.0, now]
        return None


def served_model(live) -> dict | None:
    p = live.get()
    path = getattr(p.model, "path", None)
    if path is None or path.suffix not in (".yaml", ".yml"):
        return None
    key = (str(path), live.mtime)
    got = _served.get(key)
    if got is None:
        from ..remote import compose
        from ..remote.serve import model
        with compose.offline():
            got = model(path)
        if len(_served) > 8:
            _served.clear()
        _served[key] = got
    return got


def _int(q: dict, k: str, default: int | None = None) -> int | None:
    try:
        return int((q.get(k) or [default])[0]) if (q.get(k) or [default])[0] is not None else None
    except ValueError:
        return default


def _float(q: dict, k: str) -> float | None:
    try:
        v = (q.get(k) or [None])[0]
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _list(q: dict, k: str) -> list[str]:
    return [x for v in q.get(k) or [] for x in v.split(",") if x]


def reading_of(live, p, ref: str) -> dict:
    """The newest reading of a model part, as this ergostat sees it: a stock's or auxiliary's level, a flow's rate
    per hour, a goal's measure and status."""
    from .. import state as st
    kind, _, name = ref.partition(".")
    m = p.model
    if kind in ("stock", "auxiliary") and name in m.stocks:
        got = st.stock_value(p, name)
        return {"value": got["value"], "time": got["at"], "how": f"measured by {got['sensor']}" if got["sensor"] else None}
    snap = live.snapshot(p, st.WINDOW, None)
    if kind == "flow" and name in snap["flows"]:
        f = snap["flows"][name]
        return {"value": f["rate"], "time": snap["at"], "how": f["how"], "per": "hour"}
    if kind == "goal" and name in snap["loops"]:
        lp = snap["loops"][name]
        return {"value": lp.get("value"), "time": snap["at"], "status": lp.get("status"), "setpoint": lp.get("setpoint")}
    return {"value": None, "time": None, "missing": True}


def answer(live, path: str, q: dict):
    """(status, body) for a GET under /remote/v1/."""
    parts = [unquote(x) for x in path.strip("/").split("/")]
    if len(parts) < 2 or parts[0] != "v1":
        return 404, {"error": "not found (the remote API is /remote/v1/...)"}
    head, rest = parts[1], parts[2:]
    p = live.get()
    m = p.model
    spec = getattr(m, "spec", None)
    if head == "status":
        from ..runner import running_pid
        served = served_model(live)
        return 200, {"name": m.name, "version": served and served["version"], "now": time.time(),
                     "running": bool(running_pid(p)), "last_seq": p.events.last_seq()}
    if head == "model":
        served = served_model(live)
        if served is None:
            return 404, {"error": "this model is not YAML (ergostat.toml): convert it to serve it"}
        return 200, served
    if head == "events":
        n = max(1, min(_int(q, "n", 100) or 100, EVENTS_MOST))
        after = _int(q, "after", 0) or 0
        kind = (q.get("kind") or [None])[0]
        glob = spec.items[kind].id if spec is not None and kind in spec.items else None
        if kind and glob is None:
            return 400, {"error": f"no kind {kind!r}"}
        last = p.events.last_seq()
        until_seq = after + n                                       # the cursor moves by at most n a page
        evs = p.events.query(n=None, type=(q.get("type") or [None])[0], item=(q.get("item") or [None])[0],
                             since=_float(q, "since"), until=_float(q, "until"), after_seq=after,
                             before_seq=until_seq + 1)
        if glob:
            evs = [e for e in evs if e.get("item") and fnmatch.fnmatchcase(e["item"], glob)]
        nxt = min(until_seq, last) if last is not None else after
        return 200, {"events": evs, "next": nxt, "more": bool(last is not None and nxt < last), "last_seq": last}
    if head == "items":
        from ..spec import items as its
        if rest:
            got = its.detail(p.events, spec, "/".join(rest))
            return (200, got) if got is not None else (404, {"error": "no such item"})
        n = max(1, min(_int(q, "n", 100) or 100, ITEMS_MOST))
        got = its.listing(p.events, spec, kind=(q.get("kind") or [None])[0], state=(q.get("state") or [None])[0], n=n,
                          offset=_int(q, "offset", 0) or 0)
        return 200, got
    if head == "counts":
        from ..spec import items as its
        got = its.listing(p.events, spec, n=1)
        return 200, {"kinds": {k["name"]: k["counts"] for k in got["kinds"]}, "total": got["total"]}
    if head == "readings":
        series, refs = _list(q, "series"), _list(q, "ref")
        if len(series) + len(refs) > READINGS_MOST:
            return 400, {"error": f"at most {READINGS_MOST} series and parts a call"}
        out: dict = {"now": time.time(), "series": {}, "refs": {}}
        served = served_model(live)
        out["version"] = served and served["version"]
        for s in series:
            got = p.measurements.latest(s)
            out["series"][s] = {"value": got[1], "time": got[0]} if got else {"value": None, "time": None}
        for r in refs:
            out["refs"][r] = reading_of(live, p, r)
        return 200, out
    if head == "series":
        name = (q.get("name") or [None])[0]
        if not name:
            return 400, {"error": "name: the series"}
        now = time.time()
        since = _float(q, "since") or now - 86400.0
        until = _float(q, "until") or now
        n = max(1, min(_int(q, "n", POINTS_MOST) or POINTS_MOST, POINTS_MOST))
        pts = p.measurements.range(name, since, until, last=n)
        return 200, {"name": name, "since": since, "until": until, "points": pts}
    if head == "process":
        if spec is None:
            return 200, {"kind": "process", "kinds": [], "nodes": [], "edges": []}
        from .. import process as pm
        from .. import state as st
        now = time.time()
        since = _float(q, "since") or now - st.WINDOW
        kinds = [k for k in ",".join(q.get("kinds") or []).split(",") if k in spec.items] or pm.kinds_of(spec, None)
        return 200, pm.process(p.events, spec, kinds, since, now, (q.get("by") or [None])[0], 0.0)
    return 404, {"error": f"no {head} here (status, model, events, items, counts, readings, series, process)"}
