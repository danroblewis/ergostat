"""What the Items page's Graph may draw of an ``/api/items-graph`` answer, and its connected groups (SPEC §5a,
*Relations*; ``relations.js`` ``rgModel`` reads both).

- **Drawable.** The items of the projections asked (``asked`` on the answer's projections), what they wait on through a
  precedence relation however far back, and the parents of those. An item the answer holds only because a relation
  of another kind names it (a review of a gap) is not drawable. With no kind marked asked, every item is.
- **Parts.** The drawable items joined by precedence links, as connected components (union-find). A parent link
  joins nothing (an epic over unrelated work would make one part of it all): a parent is in its own part, or in its
  own dependencies'. Each drawable item's ``part`` is its component's rank: those holding active work first, then
  queued, unblocked, and so on (the Graph's status order), then the earliest start, then the least id. A Graph past
  its bound keeps whole parts in that order, each with its parents, and cuts inside only the first part that does
  not fit whole, its items by status; the Graph's note counts each line that cut leaves out."""

from __future__ import annotations

ORDER = ["active", "queued", "unblocked", "blocked", "paused", "dead", "done"]


def mark(ans: dict) -> dict:
    """``ans`` with ``part`` on each drawable item (the others have none); the items are copied, not changed."""
    items = ans.get("items") or []
    by = {x["id"]: x for x in items}
    asked = {k["name"] for k in ans.get("projections") or [] if k.get("asked")}
    preds: dict[str, list[str]] = {}
    for e in ans.get("edges") or []:
        if e.get("kind") == "precedence" and e.get("from") in by and e.get("to") in by:
            preds.setdefault(e["to"], []).append(e["from"])
    todo = [x["id"] for x in items if not asked or x.get("projection") in asked]
    seen: set[str] = set()
    while todo:                                           # each asked item and what it waits on, however far back
        a = todo.pop()
        if a not in seen:
            seen.add(a)
            todo.extend(preds.get(a, []))
    for a in list(seen):                                  # and their parents, up to the top
        g = by[a].get("group")
        while g in by and g not in seen:
            seen.add(g)
            g = by[g].get("group")
    up = {a: a for a in seen}

    def root(a: str) -> str:
        while up[a] != a:
            up[a] = up[up[a]]
            a = up[a]
        return a
    for a in seen:
        for b in [p for p in preds.get(a, []) if p in seen]:      # precedence only: a parent joins nothing
            ra, rb = root(a), root(b)
            if ra != rb:
                up[max(ra, rb)] = min(ra, rb)
    worst = len(ORDER)                                    # a status not known ranks last, never first
    key: dict[str, tuple] = {}
    for a in seen:
        x, r = by[a], root(a)
        k = (ORDER.index(x["status"]) if x.get("status") in ORDER else worst, x.get("es") or x.get("first") or 0.0, a)
        key[r] = min(key.get(r, k), k)
    rank = {r: n for n, r in enumerate(sorted(key, key=lambda r: key[r]))}
    out = [{**x, "part": rank[root(x["id"])]} if x["id"] in seen else x for x in items]
    return {**ans, "items": out}
