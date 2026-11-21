"""Queries over the items' relations and mentions (SPEC §5a, *Graph queries*), read from the item index
(``itemindex.py``): its links, both ways, and the items' fields.

- ``near(ID, depth)``: the items within ``depth`` relation hops (1 to ``DEPTH_MOST``), each with its distance and the
  step it was first reached by.
- ``path(A, B)``: a shortest chain of relations between two items (breadth first), walked either way; a step walked
  backward is named by its relation's inverse as the kind declares it (``inverse:``), else the derived one
  (``relations.inverse_of``: ``blocks``, ``children``, ``before``, ..., any other ``NAME_of``).
- ``about(ID)``: the items linking to it by a declared relation (``declared``), then those whose fields hold its id as a
  whole token (``inferred``: ``ticket/1`` is not in ``ticket/12``), among those the index's text (``items.text_of``,
  its first ``TEXT_MOST`` characters) holds it in.

Each visits at most ``VISIT`` items and says ``capped`` when it stopped there: a capped path is "none within the cap",
never "not connected". An unknown id is ``Unknown``, a bad depth ``Bad``: never an empty answer."""

from __future__ import annotations

import re

from .items import kind_of
from .relations import inverse_of

VISIT = 2000            # items a query visits at most
DEPTH_MOST = 4          # near's farthest hop


class Unknown(LookupError):
    """No item has this id."""


class Bad(ValueError):
    """A query that is not one (a depth outside 1..DEPTH_MOST, a missing end)."""


def depth_of(raw) -> int:
    if raw is None:
        return 1
    if not str(raw).isdigit() or not 1 <= int(raw) <= DEPTH_MOST:
        raise Bad(f"depth {raw!r}: a whole number of hops from 1 to {DEPTH_MOST}")
    return int(raw)


def _index(events, spec):
    from .itemindex import index_for
    ix = index_for(events, spec, False)
    if ix is None:
        raise Bad("the record keeps no item index (a record on disk does)")
    return ix


def _known(ix, *ids: str) -> None:
    have = {i.id for i in ix.items(ids=ids, moves=False)}
    for i in ids:
        if not i or i not in have:
            raise Unknown(f"no item {i!r}")


def _inverse(spec, src: str, rel: str) -> str:
    r = (getattr(kind_of(spec, src), "relations", None) or {}).get(rel)
    return getattr(r, "inverse", "") or inverse_of(rel)


def _steps(ix, spec, frontier: list[str]) -> list[tuple[str, str, str]]:
    """(from, relation, to) of every step out of ``frontier``: its links, and the links to it by their inverse."""
    out = [(a, r, d) for a, r, d in ix.links_from(frontier)]
    out += [(d, _inverse(spec, a, r), a) for a, r, d in ix.links_to(frontier)]
    return sorted(set(out))


def _walk(ix, spec, start: str, depth: int, goal: str | None = None):
    """Breadth first from ``start``: (each item reached → (distance, the step reaching it)), capped, found."""
    seen: dict[str, tuple[int, tuple | None]] = {start: (0, None)}
    frontier, d = [start], 0
    while frontier and d < depth:
        d, nxt = d + 1, []
        for a, r, b in _steps(ix, spec, frontier):
            if b in seen:
                continue
            if len(seen) >= VISIT:
                return seen, True, False
            seen[b] = (d, (a, r, b))
            nxt.append(b)
            if b == goal:
                return seen, False, True
        frontier = nxt
    return seen, False, goal is not None and goal in seen


def near(events, spec, id: str, depth=None) -> dict:
    depth = depth_of(depth)
    ix = _index(events, spec)
    with ix.lock:
        _known(ix, id)
        seen, capped, _ = _walk(ix, spec, id, depth)
    items = [{"id": b, "distance": n, "via": {"from": s[0], "relation": s[1]}}
             for b, (n, s) in seen.items() if s is not None]
    return {"query": "near", "id": id, "depth": depth, "items": items, "capped": capped, "cap": VISIT}


def path(events, spec, a: str, b: str | None) -> dict:
    if not b:
        raise Bad("path: the item it goes to (--path B, to=B)")
    ix = _index(events, spec)
    with ix.lock:
        _known(ix, a, b)
        seen, capped, found = _walk(ix, spec, a, VISIT, goal=b) if a != b else ({a: (0, None)}, False, True)
    steps, x = [], b
    while found and seen[x][1] is not None:
        f, r, t = seen[x][1]
        steps.insert(0, {"from": f, "relation": r, "to": t})
        x = f
    says = "found" if found else f"none within the cap ({VISIT} items)" if capped else "no path"
    return {"query": "path", "from": a, "to": b, "found": found, "steps": steps, "capped": capped, "says": says,
            "cap": VISIT}


def mentions(fields, token: re.Pattern) -> str | None:
    """The first field (by name) one of whose string values, nested ones too (as ``items.text_of`` reads them, never
    their JSON, where a newline would be ``\\n``), holds ``token``."""
    for f in sorted(fields):
        todo = [fields[f]]
        while todo:
            v = todo.pop()
            if isinstance(v, str) and token.search(v):
                return f
            if isinstance(v, (dict, list)):
                todo += list(v.values()) if isinstance(v, dict) else v
    return None


def about(events, spec, id: str) -> dict:
    ix = _index(events, spec)
    token = re.compile(rf"(?<![\w/-]){re.escape(id)}(?![\w/-])")
    with ix.lock:
        _known(ix, id)
        got = {a: {"id": a, "how": "declared", "relation": r} for a, r, _ in sorted(ix.links_to([id]))}
        holding = ix.items(words=(id.casefold(),), n=VISIT + 1, moves=False)   # the text index: those holding it at all
        capped = len(got) > VISIT or len(holding) > VISIT
        for it in holding[:VISIT]:
            if it.id != id and it.id not in got and (f := mentions(it.fields, token)):
                got[it.id] = {"id": it.id, "how": "inferred", "field": f}
    return {"query": "about", "id": id, "items": list(got.values())[:VISIT], "capped": capped, "cap": VISIT}
