"""The item sets a snapshot holds (SPEC §5a): exactly those its own answers link to, read from what it holds. Each
part's side-panel set (``items.set``), and each process map's nodes and lines (``process.js``, ``pmSet``). For
each, the side panel's list and the Items page opened from its link, each keyed as the page's ``snapKey`` keys
it. At most ``MOST`` sets, in a fixed order: parts as asked, then each map's nodes as it lists them, then all
the maps' lines by count, most first (equal counts as listed)."""

from __future__ import annotations

import time

from ..spec.item_sets import BadSet

MOST = 400                       # the most sets held: each is two answers
SHOWN = {"alone": "1", "n": "10", "shown": "1"}   # the side panel's list (itemsets.js itemsSection)


def _stamp(t: float) -> str:
    """As ``pmStamp``: the second, in UTC, its fraction dropped (never rounded up)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(t // 1)))


def _end(g: dict, id_: str) -> dict:
    """A line's end as ``openProcessEdge`` finds it: the map's node, else read from its id."""
    n = next((x for x in g.get("nodes") or [] if x.get("id") == id_), None)
    parts = id_.split(":")
    return n or {"itemKind": parts[1] if len(parts) > 1 else "", "activity": ":".join(parts[2:])}


def _of_line(e: dict, g: dict) -> dict:
    a, b = _end(g, e["source"]), _end(g, e["target"])
    if e.get("kind") == "related":
        return {"kind": [a["itemKind"]], "through": [a["activity"]]}
    if e.get("kind") == "caused":
        return {"kind": [b["itemKind"]], "caused": [f"{a['itemKind']}:{a['activity']}>{b['activity']}"]}
    return {"kind": [e.get("itemKind")], "followed": [f"{a['activity']}>{b['activity']}"]}


def named(data: dict) -> list[dict]:
    """Every set the held answers link to, each once, in the fixed order, the first ``MOST`` of them."""
    parts = [v["items"]["set"] for k, v in data.items() if k.startswith("part/") and isinstance(v, dict)
             and isinstance(v.get("items"), dict) and v["items"].get("set")]
    maps = [g for k, g in data.items() if k.startswith("graph?") and isinstance(g, dict) and g.get("kind") == "process"]
    span = lambda g: {"by": [g.get("by")], "moved_since": [_stamp(g["since"])], "moved_until": [_stamp(g["until"])]}   # noqa: E731
    nodes = [{"kind": [n.get("itemKind")], "through": [n.get("activity")], **span(g)}
             for g in maps for n in g.get("nodes") or [] if n.get("kind") != "schedule"]
    lines = sorted(((e.get("count") or 0, {**_of_line(e, g), **span(g)}) for g in maps for e in g.get("edges") or []),
                   key=lambda x: -x[0])
    out: dict[str, dict] = {}
    for s in [*parts, *nodes, *(s for _, s in lines)]:
        out.setdefault(page_key(s), s)
    return list(out.values())[:MOST]


def flat(s: dict) -> dict:
    """A set's params as the page holds them: a list as JavaScript's ``String`` says it (``a,b``)."""
    return {k: ",".join(str(x) for x in vs) for k, vs in s.items()}


def page_key(s: dict, extra: dict | None = None) -> str:
    from .snapshot import key
    return key("items", {**flat(s), **(extra or {})})


def hold(data: dict, ask) -> None:
    """Both answers for every set named: ``ask(params)`` is the live answer to an Items query of lists. A set the
    server says is not one (``BadSet``) is left out; any other failure stops the snapshot."""
    for s in named(data):
        for extra in (SHOWN, {}):
            try:
                got = ask({**s, **{k: [v] for k, v in extra.items()}})
            except BadSet:
                break
            if got is None:
                raise RuntimeError(f"items: no answer for the set {flat(s)}")
            data[page_key(s, extra)] = got
