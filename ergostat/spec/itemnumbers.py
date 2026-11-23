"""An item's numeric fields as numbers over time (SPEC §5a): what the item index keeps in ``number_log`` and
``numbers``, so a chart reads one kind's field over a window without decoding a document or reading the record.

A value is a plain int or float at the top of an item's document. A boolean is not, nor a string that looks like a
number, nor an id or a timestamp (by its name, or a value that can only be a moment). Each row is one change of one
field: when, the value it took (None: it stopped being a number), and by how much it moved, so "spent per hour" is the
sum of the moves in each hour. A snapshot carries its item's rows (``rollup.numbers``), so a record rolled up folds to
the same numbers as the events it replaced."""

from __future__ import annotations

import math
import re

from .items import SNAPSHOT, Item, fold

NOT_A_MEASURE = re.compile(r"(^|_)(id|ids|pid|seq|sha|port|at|time|times|ts|timestamp|since|until|when|date|started|"
                           r"ended|finished|created|updated|deadline|expires)$", re.I)
MOMENT = (1e9, 1e11)        # a value here is a Unix time, in seconds (2001 to 5138), whatever its field is called
UNITS = (("_usd", "usd"), ("_hours", "hours"), ("_minutes", "minutes"), ("_seconds", "seconds"), ("_lines", "lines"))


def is_value(name: str, v) -> bool:
    """Whether a field's value is a number to chart."""
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        return False
    return not NOT_A_MEASURE.search(name) and not MOMENT[0] <= abs(v) < MOMENT[1]


def values(fields: dict) -> dict[str, float]:
    """The numeric values among an item's fields."""
    return {k: float(v) for k, v in fields.items() if is_value(k, v)}


def unit_of(field: str) -> str:
    """A field's unit, where its name declares one (``ai_cost_usd``, ``loop_hours``, ``net_lines``); else a count."""
    low = field.lower()
    return next((u for suffix, u in UNITS if low.endswith(suffix)), "lines" if low == "lines" else "count")


def _carried(e: dict, transcript: bool, it: Item) -> list[tuple]:
    """The rows a snapshot carries; one written before snapshots carried them: its values, at its time."""
    r = (e.get("data") or {}).get("rollup") or {}
    if transcript and r.get("transcript"):
        r = r["transcript"]
    if r.get("numbers") is not None:
        return [tuple(x) for x in r["numbers"]]
    return [(f, e["time"], v, v) for f, v in values(it.fields).items()]


def follow(id: str, events: list[dict], kind, it: Item | None, transcript: bool, fold=fold) -> tuple[Item, list[tuple], bool]:
    """``fold`` of ``events`` into ``it``, an event at a time: the item, the rows of the changes to its numbers
    ``(field, time, value, delta)``, and whether a snapshot replaced what came before them."""
    was = values(it.fields) if it is not None else {}
    rows: list[tuple] = []
    restored = False
    for e in events:
        it = fold(id, [e], kind, it=it, transcript=transcript)
        now = values(it.fields)
        if e["type"] == SNAPSHOT:
            rows, restored = _carried(e, transcript, it), True
        elif now != was:
            rows += [(f, e["time"], now.get(f), (now.get(f) or 0.0) - (was.get(f) or 0.0))
                     for f in sorted(now.keys() | was.keys()) if now.get(f) != was.get(f)]
        was = now
    return it, rows, restored


def history_of(id: str, events: list[dict], kind, transcript: bool) -> list[list]:
    """Every change of an item's numbers over ``events``, oldest first, one row per field and moment: what a snapshot
    of them carries."""
    _, rows, _ = follow(id, events, kind, None, transcript)
    out: dict[tuple, list] = {}
    for f, t, v, d in rows:
        got = out.get((f, t))
        if got is None:
            out[(f, t)] = [f, t, v, d]
        else:
            got[2], got[3] = v, got[3] + d
    return list(out.values())
