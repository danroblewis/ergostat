"""A remote's process map, drawn beside this model's (SPEC §4c, §5b): read from the remote (``/remote/v1/process``),
kept for its ``every``, its kinds named as its parts are (``incidents-incident``) and marked remote. Lines between
our items and its items are not drawn: no event here names an item there."""

from __future__ import annotations

import threading
import time

from . import client

_kept: dict[str, tuple[float, dict | None, str]] = {}
_lock = threading.Lock()


def fetched(spec, name: str, since: float, by: str | None) -> tuple[dict | None, str]:
    r = spec.remotes[name]
    key = f"{name}|{r['url']}|{int(since // max(1.0, r['every']))}|{by}"
    with _lock:
        got = _kept.get(key)
    if got and time.time() - got[0] < r["every"]:
        return got[1], got[2]
    token, why = client.token_of(r.get("token_file"), spec.root)
    body = None
    if token is not None:
        code, body, _, why = client.get(r["url"], "process", token, {"since": since, "by": by}, timeout=10.0)
        if code != 200:
            body = None
    with _lock:
        if len(_kept) > 32:
            _kept.clear()
        _kept[key] = (time.time(), body, why)
    return body, why


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


def merge(spec, got: dict, system: str | None, since: float, by: str | None) -> dict:
    """The local map with each remote's in view (all of them, or the one the system being viewed is in) beside it."""
    from . import system_remote
    remotes = getattr(spec, "remotes", None) or {}
    if not remotes:
        return got
    mine = system_remote(spec, system)
    out = {**got, "nodes": list(got.get("nodes") or []), "edges": list(got.get("edges") or []),
           "kinds": list(got.get("kinds") or []), "remotes": {}}
    for name in remotes:
        if system and name != mine:
            continue
        body, why = fetched(spec, name, since, by)
        out["remotes"][name] = {"ok": body is not None, "why": why}
        if body is None:
            continue
        r = renamed(name, body)
        out["nodes"] += r["nodes"]
        out["edges"] += r["edges"]
        out["kinds"] += r["kinds"]
    return out
