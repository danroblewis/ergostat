"""Goals held per item or per group (SPEC §8, ``per:``): a goal on a stock counted from items, held by each item the
stock's sensor counts (``per: item``: its hours in its state, or since first seen) or by each group of them (``per:
FIELD``: the items grouped by what the field holds, each id of a relation; each group's count, oldest or age).

The goal's value is the worst one; it is off while any breaks the setpoint, and names those that do. Read from the
item index, as the stock's own count is, at any moment (``until``)."""

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


def worst(spec, g, r: float | None = None, events=None, until: float = 0.0) -> tuple[float, list[dict], int] | None:
    """(the worst value, those that break the setpoint, worst first, at most SHOWN: ``{"item" or "group", "value"}``,
    how many break it in all); None when the goal is not held per item or group."""
    s = sensor_of(spec, g) if g.per else None
    if s is None:
        return None
    q = s.items
    _, _, got = in_states(events, spec, q["kind"], q.get("state") or None, q.get("where") or {}, until=until, items=True)
    m = q.get("measure") or "count"

    def hours(it) -> float:
        return max(0.0, (until - (it.first if m == "age" else it.entered)) / 3600)
    if g.per == "item":
        units = [("item", it.id, hours(it)) for it in got]
    else:
        groups: dict = {}
        for it in got:
            for k in _keys(field_at(it.fields, g.per)):
                groups[k] = max(groups.get(k, 0.0), hours(it)) if m != "count" else groups.get(k, 0.0) + 1
        units = [("group", k, v) for k, v in groups.items()]
    low = -1 if g.hold.op in (">=", ">") else 1                 # nearest the setpoint's bad side first, when none is off
    units.sort(key=lambda u: (abs(g.hold.error(u[2], r)), low * u[2]), reverse=True)
    off = [{u[0]: u[1], "value": round(u[2], 3)} for u in units if g.hold.outside(u[2], g.tolerance, r)]
    return (units[0][2] if units else 0.0), off[:SHOWN], len(off)


def says(lp: dict) -> str:
    """The items or groups that break a goal, in words: ``ticket/3 (73.2), ticket/9 (50.1) and 2 more``."""
    b = lp.get("breaking") or []
    named = ", ".join(f"{x.get('item', x.get('group'))} ({x['value']:g})" for x in b[:5])
    more = lp.get("breaking_n", len(b)) - min(5, len(b))
    return named + (f" and {more} more" if more > 0 else "")
