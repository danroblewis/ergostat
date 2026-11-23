"""The answers that are not one value per time bucket: a non-time X (paired, per item, per category, binned), candles
and a frequency response. Each is built from what ``engine`` reads, and raises ``Unanswerable`` in words."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from . import axes, candles, labels, points, sources, spread
from . import frequency as fr
from . import transforms as tf
from .buckets import Grid, aggregate, grid
from .parse import NO_AGG, RATE_PER, Query
from .sources import OHLC_SOURCES, READERS, Unanswerable, overhangs, series_grid

FINE = 4096                 # buckets a frequency response reads its two signals on, before resampling
MOST_GROUPS = 12
OTHER = "other"


@dataclass
class Asking:
    p: object
    spec: object
    since: float
    until: float
    points: int
    one: Callable               # (query, points) -> a time result
    read: Callable              # (query, grid) -> what its source holds, under the request's budget


def label(q: Query) -> str:
    return q.field or q.series or q.measure or q.type or q.source


def _time(a: Asking, q: Query, points_: int | None = None) -> dict:
    got = a.one(q, points_ or a.points)
    if "error" in got:
        raise Unanswerable(got["error"])
    return got


def _x_meta(ty: str, name: str, unit: str, scale: str = "number", **more) -> dict:
    return {"type": ty, "label": name, "unit": unit, "scale": scale, **more}


def _base(q: Query, x: dict, series: list[dict], unit: str, capped: int, read_log: bool, notes: list[str]) -> dict:
    got = {"id": q.id, "x": x, "series": series, "unit": unit, "capped": capped, "read_log": read_log}
    if notes:
        got["note"] = "; ".join(notes)
    return got


def _grid_of(a: Asking, q: Query, points_: int, asked: float | None) -> Grid:
    if q.source == "series":
        return series_grid(a.p.measurements, q.series, a.since, a.until, points_, asked)
    return grid(a.since, a.until, points_, asked)


def _common(a: Asking, qs: tuple[Query, Query], points_: int) -> float:
    """One bucket width both can be read on: the coarser asked for, and a multiple of any roll-up tier that answers
    either (a series may need a wider step than the other query asked for)."""
    step = max(_grid_of(a, q, points_, q.bucket).step for q in qs)
    for _ in range(6):
        wider = max(_grid_of(a, q, points_, step).step for q in qs)
        if wider == step:
            return step
        step = wider
    raise Unanswerable("the two series' roll-ups share no bucket width")


def _both(a: Asking, q: Query, xq: Query) -> tuple[dict, dict]:
    """The two on one time grid."""
    step = _common(a, (q, xq), a.points)
    return (_time(a, replace(q, x=None, bucket=step)), _time(a, replace(xq, x=None, bucket=step)))


def _x_for(xr: dict, name: str, who: str) -> list:
    """The X series paired with a Y group: the one X there is, or the group of the same name."""
    got = {s["name"]: s["values"] for s in xr["series"]}
    if len(got) == 1:
        return next(iter(got.values()))
    if name in got:
        return got[name]
    raise Unanswerable(f"the X query has groups ({', '.join(sorted(got)[:4])}) and none is named {name!r}: {who}")


def paired(a: Asking, q: Query) -> dict:
    xq = q.x.query
    yr, xr = _both(a, q, xq)
    out = []
    for s in yr["series"]:
        xs, ys = axes.paired(_x_for(xr, s["name"], "group both alike, or give X one series"), s["values"])
        out.append({"name": s["name"], "xs": xs, "values": ys, "times": yr["times"], "ids": None})
    got = _carried(_base(q, _x_meta("query", label(xq), xr["unit"]), out, yr["unit"], yr["capped"],
                         yr["read_log"] or xr["read_log"], []), yr, xr)
    got["step"] = yr["step"]
    return got


def _capped(groups: dict[str, list]) -> tuple[dict[str, list], int]:
    if len(groups) <= MOST_GROUPS:
        return groups, 0
    ranked = sorted(groups, key=lambda n: (-len(groups[n]), n))
    keep, rest = ranked[:MOST_GROUPS], ranked[MOST_GROUPS:]
    out = {n: groups[n] for n in keep}
    out[OTHER] = sorted((r for n in rest for r in groups[n]), key=lambda r: (r.t, r.rid))
    return out, len(rest)


def _item_points(a: Asking, q: Query, xf: str, yf: str | None, most: int, extra: tuple = ()) -> tuple[dict, int]:
    """Per group, the items' points, at most ``most`` in all, the latest changed."""
    if q.source != "items":
        raise Unanswerable(f"an X of a field is for the items source, not {q.source}")
    every: list = []
    found = False
    for k in sources.kinds(a.spec, q):
        named = (xf, *([yf] if yf else []), *extra, *sources._named(q))
        ix = sources._index(a.p, a.spec, k, named)
        if not points.has_field(ix, k.name, xf) or (yf and not points.has_field(ix, k.name, yf)):
            continue
        found = True
        got = points.of_kind(ix, k.name, xf, yf, a.since, a.until, q.where)
        every += [(ix, k, pt) for pt in got]
    if not found:
        raise Unanswerable(f"no kind has both numeric fields {xf!r} and {yf!r}" if yf else f"{xf!r} is not a numeric field of any kind")
    every.sort(key=lambda r: (r[2].t, r[2].rid))
    left = max(0, len(every) - most)
    every = every[-most:]
    return _labelled(a, q, every), left


def _labelled(a: Asking, q: Query, every: list) -> dict:
    groups: dict[str, list] = {}
    by_ix: dict = {}
    for ix, k, pt in every:
        by_ix.setdefault((id(ix), k.name), (ix, k, []))[2].append(pt)
    x = q.x
    for ix, k, pts in by_ix.values():
        rids = [pt.rid for pt in pts]
        ids = points.names(ix, rids)
        label_of = labels.labeller(ix, k.name, q.group_by) if q.group_by else None
        sizes = points.held(ix, k.name, x.size, a.until) if x.size else {}
        color = labels.labeller(ix, k.name, x.color_by) if x.color_by else None
        for pt in pts:
            pt.id = ids.get(pt.rid)
            pt.size = sizes[pt.rid][1] if pt.rid in sizes else None
            pt.color = color(pt.rid) if color else None
            groups.setdefault(label_of(pt.rid) if label_of else (q.field or x.field), []).append(pt)
    if x.size and every and all(pt.size is None for _, _, pt in every):
        raise Unanswerable(f"size {x.size!r} is not a numeric field of these items")
    for pts in groups.values():
        pts.sort(key=lambda r: (r.t, r.rid))
    return groups


def _ignored(q: Query, agg_fits: bool) -> list[str]:
    out = []
    if not agg_fits:
        out.append(f"agg {q.agg} does not apply here: each point is one item")
    if q.transform != "none":
        out.append(f"transform {q.transform} does not apply to this X")
    return out


def by_field(a: Asking, q: Query) -> dict:
    from ..spec.itemnumbers import unit_of
    x = q.x
    extra = tuple(f for f in (x.size, x.color_by) if f and f not in ("state", "kind"))
    groups, left = _item_points(a, q, x.field, q.field, points.MOST_POINTS, extra)
    groups, folded = _capped(groups)
    out = []
    for name in sorted(groups, key=lambda n: (n == OTHER, n)):
        pts = groups[name]
        s = {"name": name, "xs": [r.x for r in pts], "values": [r.y for r in pts], "times": [r.t for r in pts],
             "ids": [r.id for r in pts]}
        if x.size:
            s["sizes"] = [r.size for r in pts]
        if x.color_by:
            s["colors"] = [r.color for r in pts]
        out.append(s)
    notes = _ignored(q, q.agg == NO_AGG)
    if left:
        notes.append(f"only the {points.MOST_POINTS} items changed latest are drawn, of {left + points.MOST_POINTS}")
    if folded:
        notes.append(f"{folded} groups are added up as {OTHER}")
    return _base(q, _x_meta("field", x.field, unit_of(x.field)), out, unit_of(q.field), left + folded, False, notes)


def category(a: Asking, q: Query) -> dict:
    by = q.x.by
    if q.source == "series":
        raise Unanswerable("a series has no labels to take categories from")
    if q.group_by and q.group_by != by:
        raise Unanswerable(f"this query groups by {q.group_by} and takes its X from {by}: use one of them")
    if q.agg == NO_AGG:
        return category_spread(a, q)
    if q.source == "items" and not (q.transform == "rate" and q.agg == "sum"):
        return _category_of_items(a, q)               # (a sum's rate is what moved in the window, so it reads the changes)
    g = grid(a.since, a.until, a.points)
    wanted = replace(q, x=None, group_by=by)
    read = a.read(wanted, g)
    groups = read.rows if read.rows is not None else read.levels
    size = len if read.rows is not None else (lambda r: abs(next((v for v in reversed(r) if v is not None), 0.0)))
    ranked = sorted(groups, key=lambda n: (-size(groups[n]), n))
    keep, rest = ranked[:MOST_GROUPS], ranked[MOST_GROUPS:]
    values: dict[str, float | None] = {}
    if read.rows is not None:
        pick = 2 if q.agg == "sum" else 1
        for n in keep:
            values[n] = aggregate(q.agg, [r[pick] for r in groups[n] if r[pick] is not None])
        if rest:
            values[OTHER] = aggregate(q.agg, [r[pick] for n in rest for r in sorted(groups[n], key=lambda r: r[0]) if r[pick] is not None])
    else:
        ends = {n: next((v for v in reversed(groups[n]) if v is not None), None) for n in ranked}
        values = {n: ends[n] for n in keep}
        if rest:
            values[OTHER] = sum(ends[n] or 0.0 for n in rest)
    at = {n: i for i, n in enumerate(read.order)}
    order = sorted(values, key=lambda n: (n == OTHER, at.get(n, len(at)), -(values[n] or 0.0), n)) if at else \
        sorted(values, key=lambda n: (n == OTHER, -(values[n] or 0.0), n))
    got = _category_row(a, q, order, [values[n] for n in order], read.unit, len(rest), read.read_log, [read.note] if read.note else [])
    if read.truncated:
        got["truncated"] = True
    return got


def _category_row(a: Asking, q: Query, order: list, row: list, unit: str, capped: int, read_log: bool, notes: list[str]) -> dict:
    if q.transform == "rate":
        window = a.until - a.since
        rates = [None if v is None else v / window for v in row]
        per = q.rate_per or tf.per_for(rates)
        row = [None if v is None else v * RATE_PER[per] for v in rates]
        unit = f"{unit}/{tf.SHORT[per]}" if unit else f"/{tf.SHORT[per]}"
    elif q.transform != "none":
        notes.append(f"transform {q.transform} does not apply to categories")
    return _base(q, _x_meta("category", q.x.by, "", "category"), [{"name": label(q), "xs": order, "values": row, "ids": None}],
                 unit, capped, read_log, notes)


def _category_of_items(a: Asking, q: Query) -> dict:
    """One value per item, whatever the aggregation: each item's value at the window's end, for the items changed in it.
    Its field's updates are not items: an item updated nine times counts once and weighs once in an average."""
    from ..spec.itemnumbers import unit_of
    by = q.x.by
    groups, left = _item_points(a, replace(q, group_by=by), q.field, None, points.MOST_BINNED)
    groups, folded = _capped(groups)
    values = {n: aggregate(q.agg, [r.x for r in pts if axes.finite(r.x)]) for n, pts in groups.items()}
    states = [s for k in sources.kinds(a.spec, q) for s in k.states] if by == "state" else []
    at = {s: i for i, s in reversed(list(enumerate(states)))}
    order = sorted(values, key=lambda n: (n == OTHER, at.get(n, len(at)), -(values[n] or 0.0), n))
    notes = [f"only the {points.MOST_BINNED} items changed latest are counted"] if left else []
    return _category_row(a, q, order, [values[n] for n in order], "items" if q.agg == "count" else unit_of(q.field),
                         left + folded, False, notes)


def category_spread(a: Asking, q: Query) -> dict:
    """Each category's items' values of a numeric field, as a box plot reads them: exact statistics and a bounded sample,
    from the index of numbers and never the event log."""
    from ..spec.itemnumbers import unit_of
    by = q.x.by
    if q.source != "items" or not q.field:
        raise Unanswerable("agg none on a category is for a numeric field of items")
    groups, left = _item_points(a, replace(q, group_by=by), q.field, None, points.MOST_BINNED)
    groups, folded = _capped(groups)
    states = [s for k in sources.kinds(a.spec, q) for s in k.states] if by == "state" else []
    at = {s: i for i, s in reversed(list(enumerate(states)))}
    series = []
    for name in sorted(groups, key=lambda n: (n == OTHER, at.get(n, len(at)), n)):
        ordered = sorted(r.x for r in groups[name] if axes.finite(r.x))
        if ordered:
            sent = spread.sample(ordered)
            series.append({"name": name, "xs": [name] * len(sent), "values": sent, "ids": None, "box": spread.box(ordered)})
    notes = _ignored(q, True)
    if left:
        notes.append(f"only the {points.MOST_BINNED} items changed latest are counted")
    if folded:
        notes.append(f"{folded} categories are added up as {OTHER}")
    return _base(q, _x_meta("category", by, "", "category", distribution=True), series, unit_of(q.field), left + folded, False, notes)


def _binned(q: Query, name_rows: list[tuple[str, list, list]], bins: int, x_meta: dict, unit: str, left: int, read_log: bool,
            notes: list[str]) -> dict:
    every = [x for _, xs, _ in name_rows for x in xs if axes.finite(x)]
    if not every:
        return _base(q, {**x_meta, "edges": []}, [], unit, left, read_log, notes)
    e = axes.edges(every, bins)
    mid = axes.centres(e)
    out = []
    for name, xs, ys in name_rows:
        cells: list[list] = [[] for _ in range(bins)]
        for x, y in zip(xs, ys, strict=True):
            if axes.finite(x):
                if q.agg == "count":
                    cells[axes.bin_of(x, e)].append(1.0)
                elif axes.finite(y):
                    cells[axes.bin_of(x, e)].append(y)
        out.append({"name": name, "xs": mid, "values": [aggregate(q.agg, c) for c in cells], "ids": None})
    return _base(q, {**x_meta, "edges": e}, out, unit, left, read_log, notes)


def _carried(got: dict, *read: dict) -> dict:
    """What the answers it was made from say about themselves: a chart of part of the record says so."""
    said = [n for n in (got.get("note"), *(r.get("note") for r in read)) if n]
    if said:
        got["note"] = "; ".join(dict.fromkeys(said))
    if any(r.get("truncated") for r in read):
        got["truncated"] = True
    return got


def binned(a: Asking, q: Query) -> dict:
    from ..spec.itemnumbers import unit_of
    x = q.x
    notes = [f"transform {q.transform} is applied before binning"] if q.transform != "none" and x.field is None else []
    if x.field:
        notes += [f"transform {q.transform} does not apply to items' values"] if q.transform != "none" else []
        yf = None if q.agg == "count" or q.field == x.field else q.field
        groups, left = _item_points(a, q, x.field, yf, points.MOST_BINNED)
        groups, folded = _capped(groups)
        if left:
            notes.append(f"only the {points.MOST_BINNED} items changed latest are counted")
        names = sorted(groups, key=lambda n: (n == OTHER, n))
        rows = [(n, [r.x for r in groups[n]], [r.y if yf else r.x for r in groups[n]]) for n in names]
        unit = "items" if q.agg == "count" else unit_of(yf or x.field)
        return _binned(q, rows, x.bins, _x_meta("bins", x.field, unit_of(x.field)), unit, left + folded, False, notes)
    own = replace(q, x=None, agg=sources_agg(q))
    if x.query is None:
        r = _time(a, own)
        rows = [(s["name"], s["values"], s["values"]) for s in r["series"]]
        return _carried(_binned(q, rows, x.bins, _x_meta("bins", label(q), r["unit"]), "buckets" if q.agg == "count" else r["unit"],
                                r["capped"], r["read_log"], notes), r)
    yr, xr = _both(a, own, x.query)
    rows = [(s["name"], _x_for(xr, s["name"], "group both alike, or give X one series"), s["values"]) for s in yr["series"]]
    return _carried(_binned(q, rows, x.bins, _x_meta("bins", label(x.query), xr["unit"]), "buckets" if q.agg == "count" else yr["unit"],
                            yr["capped"], yr["read_log"] or xr["read_log"], notes), yr, xr)


def sources_agg(q: Query) -> str:
    """What each bucket of a binned query holds: a histogram's own ``count`` counts buckets, of the source's usual value."""
    from .parse import DEFAULT_AGG
    return ("p50" if q.measure == "time_in_state" else DEFAULT_AGG[q.source]) if q.agg == "count" else q.agg


def ohlc(a: Asking, q: Query, first_time) -> dict:
    if q.source not in OHLC_SOURCES:
        raise Unanswerable(f"{q.source} has no values in time to open and close: candles are for {', '.join(OHLC_SOURCES)}")
    if q.source == "moves" and q.measure != "time_in_state":
        raise Unanswerable("candles of moves are of time_in_state: entries and exits are counts, with no open or close")
    g = _grid_of(a, q, a.points, q.bucket)
    notes = [f"transform {q.transform} does not apply to candles"] if q.transform != "none" else []
    if q.source == "series":
        read = READERS["series"](a.p, a.spec, replace(q, agg="last"), g)
        try:
            got_rows = candles.of_series(a.p.measurements, q.series, g)
        except candles.TooMany as e:
            raise Unanswerable(str(e)) from e
        if 0 in got_rows and overhangs(a.p.measurements, q.series, g):
            del got_rows[0]                           # its open is from before the window
            notes.append("the first bucket is left empty: its roll-up began before the window")
        rows = {q.series: got_rows}
        folded, order, unit, log_read = 0, [q.series], read.unit, False
    else:
        read = READERS[q.source](a.p, a.spec, replace(q, agg="last"), g)
        groups = read.rows
        ranked = sorted(groups, key=lambda n: (-len(groups[n]), n))
        keep, rest = ranked[:MOST_GROUPS], ranked[MOST_GROUPS:]
        kept = {n: groups[n] for n in keep}
        if rest:
            kept[OTHER] = sorted((r for n in rest for r in groups[n]), key=lambda r: r[0])
        rows = {n: candles.from_readings([(t, v) for t, v, _ in r if axes.finite(v)], g) for n, r in kept.items()}
        at = {n: i for i, n in enumerate(read.order)}
        order, folded, unit, log_read = sorted(rows, key=lambda n: (n == OTHER, at.get(n, len(at)), n)), len(rest), read.unit, read.read_log
        notes += [read.note] if read.note else []
        if q.source == "items":
            from ..spec.itemnumbers import unit_of
            unit = unit_of(q.field)
    got = {"id": q.id, "times": g.times, "step": g.step, "unit": unit, "capped": folded, "read_log": log_read,
           "series": [{"name": n, **candles.columns(rows[n], g.n)} for n in order]}
    if notes:
        got["note"] = "; ".join(notes)
    if read.truncated:
        got["truncated"] = True
    return got


def _signal(a: Asking, q: Query, side: str, step: float) -> tuple[list, str, bool, dict]:
    r = _time(a, replace(q, bucket=step), FINE)
    if len(r["series"]) != 1:
        raise Unanswerable(f"the {side} has {len(r['series'])} series: a response needs one (filter it, or drop group_by)")
    return r["series"][0]["values"], r["unit"], r["read_log"], r


def response(a: Asking, q: Query) -> dict:
    if q.model:
        return _model(a, q)
    for side, sub in (("input", q.input), ("output", q.output)):
        if sub.x is not None or sub.agg == "ohlc":
            raise Unanswerable(f"the {side} must be a plain query in time")
    step = _common(a, (replace(q.input, bucket=None), replace(q.output, bucket=None)), FINE)   # one grid, whatever answers each
    g: Grid = grid(a.since, a.until, FINE, step)
    xs, xu, xl, xr = _signal(a, q.input, "input", step)
    ys, yu, yl, yr = _signal(a, q.output, "output", step)
    lo = 1 if g.spans[0] < g.step else 0          # a bucket cut by the window holds part of its sum: not a sample
    hi = g.n - 1 if g.spans[-1] < g.step else g.n
    try:
        ux, uy, dt = fr.resample(xs[lo:hi], ys[lo:hi], g.step)
        got = fr.estimate(ux, uy, dt, q.segments)
    except fr.Refused as e:
        raise Unanswerable(str(e)) from e
    return _carried({"id": q.id, **got, "method": "empirical", "unit": "" if xu == yu else f"{yu}/{xu}" if xu else yu,
                     "read_log": xl or yl}, xr, yr)


def _model(a: Asking, q: Query) -> dict:
    from ..control import loop, lti
    goals = getattr(a.spec, "goals", None) or {}
    if q.model not in goals:
        raise Unanswerable(f"goal {q.model!r} is not in the model")
    proc = loop.model_process(a.spec, q.model)
    if proc is None:
        raise Unanswerable(f"goal {q.model!r} declares no process, so there is no model response to draw")
    b = lti.bode(proc)
    mags, phases = b["process"]["mag"], b["process"]["phase"]
    kept = [i for i, m in enumerate(mags) if m > 0]
    res = [mags[i] * math.cos(math.radians(phases[i])) for i in kept]
    ims = [mags[i] * math.sin(math.radians(phases[i])) for i in kept]
    poles = [{"re": 0.0, "im": 0.0}] if proc["form"] == "integrating" else [{"re": -1 / proc["tau"], "im": 0.0}]
    return {"id": q.id, "frequency": {"hz": [b["w"][i] / (2 * math.pi) for i in kept],
                                      "magnitude_db": [20 * math.log10(mags[i]) for i in kept],
                                      "phase_deg": [phases[i] for i in kept], "re": res, "im": ims, "coherence": None},
            "method": "model", "samples": 0, "unit": "", "read_log": False, "poles": poles, "zeros": [],
            "delay_seconds": proc.get("theta") or 0.0}
