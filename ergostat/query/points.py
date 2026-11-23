"""One point per item, for an X of type ``field`` or for binning a field: the values each item held at the end of the
window, read from the index's log of numbers, never from the event log."""

from __future__ import annotations

from dataclasses import dataclass

from ..spec import numberreads
from . import labels
from .axes import finite

MOST_POINTS = 2000          # points of a scatter
MOST_BINNED = 20_000        # items a histogram counts
CHUNK = 500


@dataclass
class Point:
    rid: int
    t: float
    x: float
    y: float | None
    size: float | None = None
    color: str | None = None
    id: str | None = None


def held(ix, kind: str, field: str, until: float) -> dict[int, tuple[float, float]]:
    """Each item's value of ``field`` at ``until``: rid -> (when it was last changed, the value)."""
    k, f = ix.known(kind), ix.known(field)
    if k == -1 or f == -1:
        return {}
    rows = ix.guard(lambda: ix.db.execute(
        "select rid, max(t), value from number_log where kind = ? and field = ? and t <= ? group by rid", (k, f, until)).fetchall())
    return {r: (t, v) for r, t, v in rows if finite(v)}


def has_field(ix, kind: str, field: str) -> bool:
    return any(f["field"] == field for f in numberreads.fields_of(ix).get(kind, ()))


def names(ix, rids: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for i in range(0, len(rids), CHUNK):
        part = rids[i:i + CHUNK]
        marks = ",".join("?" * len(part))
        sql = f"select rid, id from items where rid in ({marks})"
        out.update(ix.guard(lambda s=sql, a=part: dict(ix.db.execute(s, a).fetchall())))
    return out


def of_kind(ix, kind: str, xf: str, yf: str | None, since: float, until: float, where: tuple) -> list[Point]:
    """The items changed in the window that hold both fields (``yf`` None: only X is needed)."""
    xs = held(ix, kind, xf, until)
    ys = held(ix, kind, yf, until) if yf and yf != xf else xs if yf else {}
    ok = labels.allowed(ix, kind, where)
    out = []
    for rid, (tx, x) in xs.items():
        if yf and rid not in ys:
            continue
        ty, y = ys[rid] if yf else (tx, None)
        t = max(tx, ty)
        if t >= since and (ok is None or ok(rid)):
            out.append(Point(rid, t, x, y))
    return out


def newest(points: list[Point], most: int) -> tuple[list[Point], int]:
    """At most ``most``, the latest changed, in time order; and how many were left out."""
    points = sorted(points, key=lambda a: (a.t, a.rid))
    return points[-most:], max(0, len(points) - most)
