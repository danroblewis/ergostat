"""A part drawn inside its own system's box by its short name (SPEC §2a, *A part's system*).

Only the label changes: a node, a box's measure row (``measures``, or ``charted``: the Dynamics view's sparkline rows)
or a box's port gets ``shown`` (its short name) when the system
it belongs to (``spec/belongs.py``) is drawn around it: the system drilled into, an open system's outline it sits in,
or the box whose row or port it is. Its ``label`` (its full name, which links and lookups use) is kept. A part whose
system is not known, or not drawn around it, has no ``shown``: its full name is drawn. A short name that would read
the same as anything else drawn (another part, or an open system's outline title) is dropped, so two parts never read
alike."""

from __future__ import annotations

from .spec.belongs import by_name


def shorten(g: dict, spec) -> dict:
    owners = by_name(spec)
    if not owners:
        return g
    focus = g.get("focus")

    def around(n: dict) -> set[str]:
        if n.get("kind") == "terminal":                    # outside what is drawn: the system it is in is not around it
            return set()
        return {*(n.get("systems") or []), *([focus] if focus else [])}

    def mark(x: dict, systems: set[str]) -> None:
        b = owners.get(x.get("label"))
        if b is not None and b.system in systems:
            x["shown"] = b.short
    drawn = []
    for n in g.get("nodes") or []:
        mark(n, around(n))
        drawn.append(n)
        if n.get("kind") == "system":                      # its rows and ports: inside its box
            for x in [*(n.get("measures") or []), *(n.get("charted") or []),*(n.get("ports") or [])]:
                mark(x, {n.get("label"), *around(n)})
                drawn.append(x)
    while True:                                            # never two parts alike: a clash drawn with full names
        said: dict = {s: {f"outline:{s}"} for s in g.get("open") or []}   # an open outline's title: its full name
        for x in drawn:                                    # (one part drawn twice, a row and a port, is one part)
            said.setdefault(x.get("shown") or x.get("label"), set()).add(x.get("label"))
        clash = [x for x in drawn if x.get("shown") and len(said[x["shown"]]) > 1]
        if not clash:
            return g
        for x in clash:
            del x["shown"]
