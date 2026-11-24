"""Reading the item index's numbers (``itemnumbers.py``): which fields each kind has, and one field's changes over a
window. Each read holds the index's lock (``Index.guard``) and touches no document and no event."""

from __future__ import annotations

from .itemnumbers import unit_of


def fields_of(ix) -> dict[str, list[dict]]:
    """Per kind, its numeric fields: the name, the unit its name declares, and how many items hold it now."""
    def read():
        return ix.db.execute("select kind, field, count(*) from numbers group by kind, field").fetchall()
    out: dict[str, list[dict]] = {}
    for k, f, n in ix.guard(read):
        name = ix.name(f)
        out.setdefault(ix.name(k) or "", []).append({"field": name, "unit": unit_of(name), "items": n})
    for got in out.values():
        got.sort(key=lambda x: x["field"])
    return out


def changes(ix, kind: str, field: str, since: float, until: float) -> list[tuple[float, int, float | None, float]]:
    """``(time, item's rid, value, delta)`` of each change of ``kind``'s ``field`` in the window, oldest first."""
    k, f = ix.known(kind), ix.known(field)
    if k == -1 or f == -1:
        return []
    return ix.guard(lambda: ix.db.execute(
        "select t, rid, value, delta from number_log where kind = ? and field = ? and t >= ? and t <= ? order by t",
        (k, f, since, until)).fetchall())
