"""One point per item, for an X of type ``field`` or for binning a field: the values each item held at the end of the
window, read by one SQL query over the item views (``sources.item_points``), never from the event log."""

from __future__ import annotations

from dataclasses import dataclass

MOST_POINTS = 2000          # points of a scatter
MOST_BINNED = 20_000        # items a histogram counts


@dataclass
class Point:
    rid: object             # the item, as the points are ordered (its id)
    t: float
    x: float
    y: float | None
    size: float | None = None
    color: str | None = None
    id: str | None = None
