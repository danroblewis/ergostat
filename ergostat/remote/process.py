"""A remote's process map, drawn beside this model's (SPEC §4c, §5b): read from the remote (``/remote/v1/process``),
kept for its ``every``, its kinds named as its parts are (``incidents-incident``) and marked remote.

Lines between our items and its items come from a relation naming the remote's kind (``blocked_by:
incidents-incident``, SPEC §5a): our item holds the remote item's id. The ids are sent with the same request
(``at=``, at most ``AT_MOST``, chosen by id, never by time), the remote says the step each was last at, and a line
is drawn from our item's last step to that step. A link that cannot be drawn is never dropped: it is counted in
``unlinked`` by its reason, so ``linked`` and ``unlinked`` add up to every link. No time of the remote's is
compared with one of ours."""

from __future__ import annotations

import hashlib
import threading
import time
from urllib.parse import urlencode

from ..web.remote_api import AT_MOST
from . import client

AT_BYTES = 32_000                    # the url-encoded at= query, at most
ID_MOST = 128                        # an id sent, at most this many characters
_kept: dict[str, tuple] = {}
_lock = threading.Lock()


def fetched(spec, name: str, since: float, by: str | None, at: tuple[str, ...] = ()) -> tuple[dict | None, str, bool]:
    """(the remote's map, why not, whether it is the map as last read). Kept by the ids sent (a reply's ``at`` is only
    ever for exactly those), and by the remote alone: unreachable, its map as last read in the window is drawn, its
    ``at`` only if it was for the same ids. The cache is read under the lock, then the GET and the write are made
    outside it, on purpose: two at once both GET, and the last write wins with an answer as good as the other's
    (an idempotent read-through: nothing is decided from what was read)."""
    r = spec.remotes[name]
    base = f"{name}|{r['url']}|{int(since // max(1.0, r['every']))}|{by}"
    key = f"{base}|{hashlib.sha256(chr(10).join(at).encode()).hexdigest()[:16]}"
    with _lock:
        got, last = _kept.get(key), _kept.get(base)
    if got and time.time() - got[0] < r["every"]:
        body, why = got[1], got[2]
    else:
        token, why = client.token_of(r.get("token_file"), spec.root)
        body = None
        if token is not None:
            code, body, _, why = client.get(r["url"], "process", token,
                                            {"since": since, "by": by, "at": list(at) or None}, timeout=10.0,
                                            tls=r.get("tls"))
            if code != 200 or not isinstance(body, dict):
                body = None
        with _lock:
            if len(_kept) > 30:                     # two written a call: never past 32
                _kept.clear()
            _kept[key] = (time.time(), body, why)
            if body is not None:
                _kept[base] = (time.time(), body, why, key)
    if body is None and last is not None:
        return (last[1] if last[3] == key else {k: v for k, v in last[1].items() if k != "at"}), why, True
    return body, why, False


def renamed(name: str, got: dict) -> dict:
    """The remote's map with its kinds named as its parts are here, so they never meet this model's."""
    k = lambda x: f"{name}-{x}"                     # noqa: E731
    ids = {}
    nodes = []
    for n in got.get("nodes") or []:
        new = {**n, "itemKind": k(n["itemKind"]), "id": f"p:{k(n['itemKind'])}:{n.get('activity')}", "remote": name}
        ids[n["id"]] = new["id"]
        nodes.append(new)
    edges = []
    for e in got.get("edges") or []:
        if e.get("source") not in ids or e.get("target") not in ids:
            continue
        edges.append({**e, "id": f"r:{name}:{e['id']}", "source": ids[e["source"]], "target": ids[e["target"]],
                      **({"itemKind": k(e["itemKind"])} if e.get("itemKind") else {}), "remote": name})
    kinds = [{**x, "name": k(x["name"]), "remote": name} for x in got.get("kinds") or []]
    return {"nodes": nodes, "edges": edges, "kinds": kinds}


def sendable(x) -> bool:
    """An id that may be sent (an allowlist): 1 to ``ID_MOST`` characters, none of them a space or a control."""
    return isinstance(x, str) and 0 < len(x) <= ID_MOST and all(c.isprintable() and not c.isspace() for c in x)


def chosen(ids) -> tuple[list[str], set[str], set[str]]:
    """(the ids sent, those refused, those left out): distinct, by id string ascending, while the count stays within
    ``AT_MOST`` and the encoded query within ``AT_BYTES``."""
    good = sorted({x for x in ids if sendable(x)})
    taken: list[str] = []
    size = 0
    for x in good:
        size += len(urlencode({"at": x})) + (1 if taken else 0)
        if len(taken) >= AT_MOST or size > AT_BYTES:
            break
        taken.append(x)
    return taken, {x for x in ids if not sendable(x)}, set(good[len(taken):])


def why_not(link: dict, name: str, body, at, drawn: set, here: set) -> str | None:
    """Why a link to a taken id is not drawn, or None: drawn."""
    if body is None:
        return "unreachable"
    got = at.get(link["target"]) if isinstance(at, dict) else None
    if not isinstance(got, dict) or not isinstance(got.get("kind"), str) or not isinstance(got.get("activity"), str):
        return "not-answered"
    if got["kind"] != link["there"]:
        return "other-kind"
    if f"p:{name}-{got['kind']}:{got['activity']}" not in drawn:
        return "not-drawn"
    return None if f"p:{link['kind']}:{link['activity']}" in here else "not-drawn-here"


def lines(name: str, links: list[dict], body, bad, capped, drawn: set, here: set) -> tuple[list[dict], dict]:
    """The lines from our items to the remote's (aggregated as local related lines are), and the links not drawn by
    reason. Refused and left-out ids are decided before the request, so they count so even when it is unreachable."""
    edges: dict[str, dict] = {}
    unlinked: dict[str, int] = {}
    at = body.get("at") if isinstance(body, dict) else None
    for x in links:
        t = x["target"]
        why = "bad-id" if t in bad else "capped" if t in capped else why_not(x, name, body, at, drawn, here)
        if why:
            unlinked[why] = unlinked.get(why, 0) + 1
            continue
        b, rk = at[t]["activity"], f"{name}-{x['there']}"
        key = f"x:{name}:{x['relation']}:{x['kind']}:{x['activity']}>{rk}:{b}"
        e = edges.setdefault(key, {"id": key, "kind": "related", "remote": name, "relation": x["relation"],
                                   "source": f"p:{x['kind']}:{x['activity']}", "target": f"p:{rk}:{b}",
                                   "itemKind": x["kind"], "relKind": rk, "from": x["activity"], "to": b, "count": 0,
                                   "rework": False, "self": False, "median": None, "timed": 0, "_i": set(), "_t": set()})
        e["count"] += 1
        e["_i"].add(x["item"])
        e["_t"].add(t)
    out = [{**{k: v for k, v in e.items() if not k.startswith("_")}, "items": len(e["_i"]), "targets": len(e["_t"])}
           for e in sorted(edges.values(), key=lambda e: (-e["count"], e["id"]))]
    return out, unlinked


def merge(spec, got: dict, system: str | None, since: float, by: str | None) -> dict:
    """The local map with each remote's in view (all of them, or the one the system being viewed is in) beside it,
    and the lines from our items to its items."""
    from . import system_remote
    remotes = getattr(spec, "remotes", None) or {}
    if not remotes:
        return got
    mine = system_remote(spec, system)
    out = {**got, "nodes": list(got.get("nodes") or []), "edges": list(got.get("edges") or []),
           "kinds": list(got.get("kinds") or []), "remotes": {}}
    here = {n["id"] for n in out["nodes"]}
    for name in remotes:
        if system and name != mine:
            continue
        links = [x for x in got.get("remote_links") or [] if x.get("remote") == name]
        taken, bad, capped = chosen([x["target"] for x in links])
        body, why, cached = fetched(spec, name, since, by, tuple(taken))
        out["remotes"][name] = {"ok": body is not None and not cached, "why": why, **({"cached": True} if cached else {})}
        r = renamed(name, body) if body is not None else {"nodes": [], "edges": [], "kinds": []}
        drawn, unlinked = lines(name, links, body, bad, capped, {n["id"] for n in r["nodes"]}, here)
        out["remotes"][name].update(linked=sum(e["count"] for e in drawn), unlinked=unlinked)
        out["nodes"] += r["nodes"]
        out["edges"] += r["edges"] + drawn
        out["kinds"] += r["kinds"]
    return out
