"""Goals held per item or per group (SPEC §8, ``per:``): a goal on a stock counted from items, held by each item the
stock's sensor counts (``per: item``: its hours in its state, or since first seen) or by each group of them (``per:
FIELD``: the items grouped by what the field holds, each id of a relation; each group's count, oldest or age).

The goal's value is the worst one; it is off while any breaks the setpoint, and names those that do. With no items
(no groups) nothing breaks it: its value is 0, or the setpoint itself where 0 would break it (a floor), so it holds.
The items are read from the item index (``members``), as the stock's own count is, at any moment (``until``); what
they are held to is worked out from them in memory (``held``), so a reader keeps them while the record is unchanged."""

from __future__ import annotations

from .items import field_at, in_states

SHOWN = 20             # the most that break a goal named in its event and its status; the count says how many in all


def sensor_of(spec, g):
    """The ``items:`` sensor on the stock a goal is about, or None."""
    st = spec.stocks.get(g.of.name) if g.of.kind == "stock" else None
    return next((s for s in (st.sensors.values() if st else ()) if s.items), None)


def _keys(v) -> list:
    """The groups an item belongs to by a field's value: each id of a list (a relation), else the value itself."""
    vs = v if isinstance(v, list) else [v]
    return [x for x in vs if x is not None and x != "" and not isinstance(x, dict | list)]


def members(spec, g, events, until: float) -> list[tuple] | None:
    """The stock's items as they stood at ``until``: (id, entered, first, the groups it is in); None when the goal is
    not held per item or group."""
    s = sensor_of(spec, g) if g.per else None
    if s is None:
        return None
    q = s.items
    _, _, got = in_states(events, spec, q["kind"], q.get("state") or None, q.get("where") or {}, until=until, items=True)
    return [(it.id, it.entered, it.first, [] if g.per == "item" else _keys(field_at(it.fields, g.per))) for it in got]


def held(spec, g, rows: list[tuple], r: float | None, until: float) -> tuple[float, list[dict], int]:
    """(the worst value, those that break the setpoint, worst first, at most SHOWN: ``{"item" or "group", "value"}``,
    how many break it in all)."""
    m = (sensor_of(spec, g).items.get("measure") or "count")

    def hours(row) -> float:
        return max(0.0, (until - (row[2] if m == "age" else row[1])) / 3600)
    if g.per == "item":
        units = [("item", row[0], hours(row)) for row in rows]
    else:
        groups: dict = {}
        for row in rows:
            for k in row[3]:
                groups[k] = max(groups.get(k, 0.0), hours(row)) if m != "count" else groups.get(k, 0.0) + 1
        units = [("group", k, v) for k, v in groups.items()]
    if not units:                                               # nothing to hold: it holds
        return (0.0 if not g.hold.outside(0.0, 0.0, r) else (g.hold.value if r is None else r)), [], 0
    low = -1 if g.hold.op in (">=", ">") else 1                 # nearest the setpoint's bad side first, when none is off
    units.sort(key=lambda u: (abs(g.hold.error(u[2], r)), low * u[2]), reverse=True)
    off = [{u[0]: u[1], "value": round(u[2], 3)} for u in units if g.hold.outside(u[2], g.tolerance, r)]
    return units[0][2], off[:SHOWN], len(off)


def worst(spec, g, r: float | None = None, events=None, until: float = 0.0) -> tuple[float, list[dict], int] | None:
    """``held`` of the items as they stood at ``until``; None when the goal is not held per item or group."""
    rows = members(spec, g, events, until)
    return None if rows is None else held(spec, g, rows, r, until)


def cascade_setpoint(spec, measurements, g, until: float) -> float | None:
    """The setpoint an outer block last gave a goal (a cascade, SPEC §9), as of ``until``; None when none does."""
    for b in spec.blocks.values():
        if any(t.kind == "goal" and t.name == g.name for t in b.targets()):
            got = measurements.latest(f"block/{b.name}", until)
            if got is not None:
                return got[1]
    return None


def says(lp: dict) -> str:
    """The items or groups that break a goal, in words: ``ticket/3 (73.2), ticket/9 (50.1) and 2 more``."""
    b = lp.get("breaking") or []
    named = ", ".join(f"{x.get('item', x.get('group'))} ({x['value']:g})" for x in b[:5])
    more = lp.get("breaking_n", len(b)) - min(5, len(b))
    return named + (f" and {more} more" if more > 0 else "")
