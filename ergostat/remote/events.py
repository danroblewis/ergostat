"""A remote's events, read in place (SPEC §4c): by ``seq`` cursor, a page of at most 1,000 at a time and at most
five pages a read, into a cache kept in memory and bounded by a window (one day) and a count (20,000). The cursor is
the last ``seq`` read. The local record never holds them, and the local fold never folds them.

A remote is read at most once a period (its ``every``, clamped as ``items.period``): one per-remote lock is held
across the check, the status call, the pages, the cursor and the trim, so polls from many pages read it once. Only
events past the cursor are kept, in ``seq`` order; an answer whose ``last_seq`` is below the cursor means the remote's
record was made again, and what was kept is dropped. A failed read keeps what was read before, marked ``ok: false``."""

from __future__ import annotations

import threading
import time

from . import cache, client, items

PAGE, PAGES = 1000, 5
WINDOW, MOST = 86400.0, 20000
_kept: dict[str, dict] = {}
_shown: dict[str, dict] = {}                                # a copy of the last read view, for a caller that timed out
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(name: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(name, threading.Lock())


def _view(kept: dict, now: float) -> dict:
    return {"events": list(kept["events"]), "cursor": kept["cursor"], "read": kept["read"], "ok": kept["ok"],
            "why": kept["why"], "age": None if kept["read"] is None else max(0.0, now - kept["read"])}


def _read(spec, r: dict, kept: dict) -> None:
    """Bring ``kept`` up to date: its ok and why say how; the caller holds the lock."""
    token, why = client.token_of(r.get("token_file"), spec.root)
    if token is None:
        kept["ok"], kept["why"] = False, why
        return
    if kept["cursor"] is None:                              # the first read starts at the window, not the beginning
        code, st, _, why = client.get(r["url"], "status", token, timeout=cache.TIMEOUT, tls=r.get("tls"))
        if code == 200 and not (isinstance(st, dict) and isinstance(st.get("last_seq", 0) or 0, int)):
            code, why = -1, "unexpected answer"
        if code != 200:
            kept["ok"], kept["why"] = False, why
            return
        kept["cursor"] = max(0, (st.get("last_seq") or 0) - PAGE)
    for _ in range(PAGES):
        code, body, _, why = client.get(r["url"], "events", token, {"after": kept["cursor"], "n": PAGE},
                                        timeout=cache.TIMEOUT, tls=r.get("tls"))
        if code == 200 and not (isinstance(body, dict) and isinstance(body.get("events"), list)
                                and isinstance(body.get("next"), int)):
            code, why = -1, "unexpected answer"
        if code != 200:
            kept["ok"], kept["why"] = False, why
            return
        last = body.get("last_seq")
        if isinstance(last, int) and last < kept["cursor"]:     # its record made again: what was kept is not of it
            kept["events"], kept["cursor"] = [], max(0, last - PAGE)
            continue
        new = sorted((e for e in body["events"] if isinstance(e, dict) and isinstance(e.get("seq"), int)
                      and e["seq"] > kept["cursor"]), key=lambda e: e["seq"])
        kept["events"].extend(new)
        kept["cursor"] = max(kept["cursor"], body["next"], *(e["seq"] for e in new))
        kept["ok"], kept["why"], kept["read"] = True, "", time.time()
        if not body.get("more"):
            break
    since = time.time() - WINDOW                               # the day-long window, then the count
    timed = [e for e in kept["events"] if type(e.get("time")) in (int, float) and e["time"] == e["time"]]
    if len(timed) < len(kept["events"]):                       # a time that is not a number cannot be windowed
        kept["why"] = f"{len(kept['events']) - len(timed)} events without a numeric time left out"
    kept["events"] = [e for e in timed if e["time"] >= since][-MOST:]


def follow(spec, name: str, force: bool = False) -> tuple[dict | None, str]:
    """The cache for remote ``name`` (``{"events", "cursor", "read", "ok", "why", "age"}``, a copy), read again when
    its period has passed or ``force``; None and why when nothing of it has ever been read."""
    r = (getattr(spec, "remotes", None) or {}).get(name)
    if r is None:
        return None, f"no remote {name}"
    lock, key = _lock(name), f"{name}|{r['url']}"
    if not lock.acquire(timeout=(PAGES + 1) * cache.TIMEOUT + 1.0):
        busy, last = f"{name} is busy answering another read; again shortly", _shown.get(key)
        if last is None:
            return None, busy                               # the last view, written under the lock, never the cache
        return dict(last, events=list(last["events"]), ok=False, why=busy,
                    age=max(0.0, time.time() - last["read"])), busy
    try:
        kept = _kept.setdefault(key, {"events": [], "cursor": None, "read": None, "asked": None, "ok": None, "why": ""})
        now = time.time()
        if force or kept["asked"] is None or now - kept["asked"] >= items.period(r):
            kept["asked"] = now                             # this period's read, answered or not
            _read(spec, r, kept)
        view = _view(kept, time.time())
        if view["read"] is not None:
            _shown[key] = _view(kept, view["read"])
    finally:
        lock.release()
    return (view, view["why"]) if view["read"] is not None else (None, view["why"] or "not read yet")


def newest(spec, name: str, n: int, force: bool = False) -> tuple[list[dict] | None, str]:
    kept, why = follow(spec, name, force)
    if kept is None:
        return None, why
    return kept["events"][-n:], why
