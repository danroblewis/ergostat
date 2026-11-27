"""A remote's items, read in place for the Items page (SPEC §4c): its counts, listings, details and forecast, asked of
``/remote/v1/`` and kept in memory, bounded and failing closed.

Each remote has one lock (``_lock(name)``), held across reading the cache, deciding whether to ask (fresh? a failure
this period? the budget?), the ask, the write and the eviction. A period is the remote's ``every`` clamped to
[``LEAST``, ``MOST``]; in one period at most ``ASKS`` requests go to one remote, whatever is asked (the counter goes
up before the request, and a failed one counts). A remote that failed is not asked again in the period of its
failure. With nothing to serve, the answer is an error (``RemoteRefused``), never an empty listing."""

from __future__ import annotations

import math
import re
import threading
import time
from collections import OrderedDict
from urllib.parse import quote

from . import cache, client

ASKS = 8                                 # requests to one remote in one period, counts, listings and details together
LEAST, MOST = 10.0, 600.0                # a remote's every, clamped, is the period
KEPT = 32                                # listings, and details, cached per remote (the oldest goes first)
N_MOST, OFFSET_MOST = 500, 100_000
WAIT = 2 * cache.TIMEOUT + 1.0           # the longest a caller waits on a remote's lock (its holder asks twice at most)
ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]{0,199}")   # one /-separated segment of an id (``incident/3``)
ID_MOST = 200
FORECAST_IDS = 200                       # item ids one forecast ask names (the remote API's AT_MOST)

_state: dict[str, dict] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class RemoteRefused(Exception):
    """An answer about a remote that is not one: its HTTP status and why."""

    def __init__(self, code: int, why: str):
        super().__init__(why)
        self.code, self.why = code, why


def _lock(name: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(name, threading.Lock())


def remote(spec, name: str | None) -> dict:
    """The ``remotes:`` entry called ``name``, or 400: only a name the model declares is ever asked."""
    rs = getattr(spec, "remotes", None) or {}
    if name not in rs:
        raise RemoteRefused(400, f"no remote {name} (this model's: {', '.join(rs) or 'none'})")
    return rs[name]


def period(r: dict) -> float:
    return max(LEAST, min(MOST, float(r.get("every") or LEAST)))


def openable(item_id: str) -> bool:
    """Whether a remote item can be opened here (an allowlist): at most ``ID_MOST`` characters, ``/``-separated
    segments that each fully match ``ID`` (so none is empty), and no ``..`` anywhere."""
    return (0 < len(item_id or "") <= ID_MOST and ".." not in item_id
            and all(ID.fullmatch(s) for s in item_id.split("/")))


class held:
    """``_lock(name)``, waited on for ``WAIT`` at most: past it, 503."""

    def __init__(self, name: str):
        self.name, self.lock = name, _lock(name)

    def __enter__(self):
        if not self.lock.acquire(timeout=WAIT):
            raise RemoteRefused(503, f"{self.name} is busy answering another ask; again shortly")

    def __exit__(self, *_):
        self.lock.release()


def _ask(spec, name: str, r: dict, table: str, key, path: str, params: dict | None, shaped) -> dict:
    """One answer from the cache or the remote; the caller holds ``_lock(name)``."""
    now, every = time.time(), period(r)
    st = _state.setdefault(f"{name}|{r['url']}", {"start": now, "asks": 0, "failed": None, "why": "",
                                                  "counts": OrderedDict(), "listings": OrderedDict(),
                                                  "details": OrderedDict(), "forecasts": OrderedDict()})
    if now - st["start"] >= every:
        st["start"], st["asks"] = now, 0
    kept = st[table].get(key)

    def served(ok: bool, why: str, code: int) -> dict:
        if kept is None:
            raise RemoteRefused(code, why)
        return {"ok": ok, "why": why, "read": kept["read"], "age": max(0.0, now - kept["read"]), "body": kept["body"]}

    if kept is not None and now - kept["read"] < every:
        failed = st["failed"] is not None and st["failed"] > kept["read"]
        return served(not failed, st["why"] if failed else "", 200)
    token, why = client.token_of(r.get("token_file"), spec.root)
    if token is None:
        return served(False, why, 502)
    if st["failed"] is not None and now - st["failed"] < every:
        return served(False, st["why"], 502)
    if st["asks"] >= ASKS:
        again = math.ceil(st["start"] + every - now)
        return served(st["failed"] is None, f"{name} asked {ASKS} times this period; again in {again}s", 503)
    st["asks"] += 1                                             # counted before it goes, answered or not
    code, body, _, why = client.get(r["url"], path, token, params, timeout=cache.TIMEOUT, tls=r.get("tls"))
    if code == 404 and table == "details":                      # that item is missing there, not the remote down
        raise RemoteRefused(404, f"no such item at {name}")
    if code == 503 and table == "forecasts":                    # not worked out there yet: this ask, not the remote down
        return served(False, f"{name} is still working out its forecast; ask again shortly", 503)
    if code == 200 and not shaped(body):
        code, why = -1, "unexpected answer"
    if code != 200:
        st["failed"], st["why"] = now, why or f"{code}"
        return served(False, st["why"], 502)
    st["failed"], st["why"] = None, ""
    kept = {"body": body, "read": now}
    st[table][key] = kept
    st[table].move_to_end(key)
    while len(st[table]) > KEPT:
        st[table].popitem(last=False)
    return served(True, "", 200)


def _num(v, default: int, least: int, most: int) -> int:
    try:
        return max(least, min(most, int(v)))
    except (TypeError, ValueError):
        return default


def listing(spec, name: str, kind: str | None = None, state: str | None = None, n=100, offset=0) -> dict:
    """The remote's counts by projection and state, and a page of its items, each marked ``remote``."""
    r = remote(spec, name)
    n, offset = _num(n, 100, 1, N_MOST), _num(offset, 0, 0, OFFSET_MOST)
    with held(name):
        c = _ask(spec, name, r, "counts", "", "counts", None,
                 lambda b: isinstance(b, dict) and isinstance(b.get("projections"), dict))
        got = _ask(spec, name, r, "listings", (kind, state, n, offset), "items",
                   {"projection": kind, "state": state, "n": n, "offset": offset},
                   lambda b: isinstance(b, dict) and isinstance(b.get("items"), list))
    worse = got if not got["ok"] or got["why"] else c
    return {"remote": name, "url": r["url"], "ok": c["ok"] and got["ok"], "why": worse["why"],
            "read": min(c["read"], got["read"]), "age": max(c["age"], got["age"]), "counts": c["body"]["projections"],
            "total": got["body"].get("total", c["body"].get("total")),
            "items": [{**i, "remote": name} for i in got["body"]["items"] if isinstance(i, dict)]}


def detail(spec, name: str, item_id: str) -> dict:
    """One remote item as the remote folds it; its id checked against ``ID`` before anything is sent."""
    r = remote(spec, name)
    if not openable(item_id):
        raise RemoteRefused(400, f"{item_id[:60]!r} cannot be opened here: a remote item's id is "
                             f"/-separated segments each matching {ID.pattern}, {ID_MOST} characters at most, no ..")
    with held(name):
        got = _ask(spec, name, r, "details", item_id, f"items/{quote(item_id, safe='')}", None,
                   lambda b: isinstance(b, dict))
    return {"remote": name, "ok": got["ok"], "why": got["why"], "read": got["read"], "age": got["age"],
            "item": {**got["body"], "remote": name}}


def forecast(spec, name: str, ids: list[str] | None = None, kinds: list[str] | None = None,
             ask: dict | None = None) -> dict:
    """The remote's forecast (``forecast/v1``, numbers/forecast.py), as it last worked it out: of the items ``ids``
    (at most ``FORECAST_IDS``, each checked as ``detail`` checks one) and ``kinds``, or all it serves; with ``ask``
    (numbers/yields.py ``parse``, checked here), a group's counts asked of it there (``asked``). An answer of
    another schema is a failure, never read as no estimate. One still being worked out there (its 503) refuses this
    ask alone (503, or the last one kept, not ok), and the remote's counts, listings and details are asked as before."""
    ask = ask or {}
    if ask and not openable(ask.get("group", "")):
        raise RemoteRefused(400, f"group: /-separated segments matching {ID.pattern}, {ID_MOST} characters at most")
    r = remote(spec, name)
    ids, kinds = list(dict.fromkeys(ids or [])), sorted(set(kinds or []))
    if len(ids) > FORECAST_IDS or not all(openable(i) for i in ids):
        raise RemoteRefused(400, f"at most {FORECAST_IDS} item ids, each /-separated segments matching {ID.pattern}")
    with held(name):
        got = _ask(spec, name, r, "forecasts", (tuple(ids), tuple(kinds), tuple(sorted(ask.items()))), "forecast",
                   {"item": ids or None, "projections": ",".join(kinds) or None, **{k: str(v) for k, v in ask.items()}},
                   lambda b: isinstance(b, dict) and b.get("schema") == "forecast/v1" and isinstance(b.get("items"), dict))
    return {"remote": name, "ok": got["ok"], "why": got["why"], "read": got["read"], "age": got["age"],
            "forecast": got["body"]}
