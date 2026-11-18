"""A remote's events, read in place (SPEC §4c): by ``seq`` cursor, a page of at most 1,000 at a time and at most
five pages a read, into a cache kept in memory and bounded by a window (one day) and a count (20,000). The cursor is
the last ``seq`` read. The local record never holds them, and the local fold never folds them."""

from __future__ import annotations

import threading
import time

from . import client

PAGE, PAGES = 1000, 5
WINDOW, MOST = 86400.0, 20000
_kept: dict[str, dict] = {}
_lock = threading.Lock()


def follow(spec, name: str) -> tuple[dict | None, str]:
    """The cache for remote ``name``, brought up to date from its cursor: ``{"events", "cursor", "read"}``."""
    r = (getattr(spec, "remotes", None) or {}).get(name)
    if r is None:
        return None, f"no remote {name}"
    token, why = client.token_of(r.get("token_file"), spec.root)
    if token is None:
        return None, why
    key = f"{name}|{r['url']}"
    with _lock:
        kept = _kept.setdefault(key, {"events": [], "cursor": None, "read": None})
    if kept["cursor"] is None:                              # the first read starts at the window, not the beginning
        code, st, _, why = client.get(r["url"], "status", token)
        if code != 200:
            return (kept if kept["events"] else None), why
        last = int(st.get("last_seq") or 0)
        kept["cursor"] = max(0, last - PAGE)
    for _ in range(PAGES):
        code, body, _, why = client.get(r["url"], "events", token, {"after": kept["cursor"], "n": PAGE})
        if code != 200 or not isinstance(body, dict):
            return (kept if kept["events"] else None), why
        with _lock:
            kept["events"].extend(body.get("events") or [])
            kept["cursor"] = int(body.get("next") or kept["cursor"])
            since = time.time() - WINDOW
            kept["events"] = [e for e in kept["events"] if e.get("time", 0) >= since][-MOST:]
            kept["read"] = time.time()
        if not body.get("more"):
            break
    return kept, ""


def newest(spec, name: str, n: int) -> tuple[list[dict] | None, str]:
    kept, why = follow(spec, name)
    if kept is None:
        return None, why
    return kept["events"][-n:], why
