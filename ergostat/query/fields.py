"""``GET /api/query/fields``: what can be charted, from the model and the indexes, without reading the event log."""

from __future__ import annotations

import time

from .. import datasources
from ..spec import codec, numberreads
from ..spec import items as its
from ..spec.finished import finish_of
from . import transforms
from .axes import X_OF, X_TYPES
from .labels import STATE_GROUP, word
from .parse import AGGS, MOST_SEGMENTS, RATE_PER, SEGMENTS, TRANSFORMS
from .sources import OHLC_SOURCES, _series_unit

SAMPLE = 200                # the latest items a projection's low-cardinality fields are told from
FEW = 12                    # the most distinct values a field to group by may have
LABEL_MOST = 40             # characters: a longer value is prose, not a category
KEEP = 30.0                 # seconds an answer is kept


def _groupable(ix, k) -> list[str]:
    """``state``, ``projection``, the fields its latest items hold few distinct texts in, and its group relations holding one
    id per item (a gap's ``milestone``: a category by declaration, however many) with ``state_group``, each item's stage
    in that group's progress (``item_state_groups``), to stack them by."""
    from ..spec.grouptally import offered
    groups = [r for r, x in k.relations.items() if offered(k, x)]
    kn = ix.known(k.name)
    rows = [] if kn == -1 else ix.guard(lambda: ix.db.execute(
        "select body from items where kind = ? order by last desc limit ?", (kn, SAMPLE)).fetchall())
    seen: dict[str, list] = {}
    for (body,) in rows:
        for name, v in codec.unpack(body)["f"].items():
            if isinstance(v, str | bool) and name not in k.relations and len(str(v)) <= LABEL_MOST:
                seen.setdefault(name, []).append(word(v))
    least = max(2, len(rows) // 10)               # held by a tenth of them, each value on average twice: a category
    few = [f for f, vals in seen.items() if len(vals) >= least and 1 < len(set(vals)) <= FEW and len(vals) >= 2 * len(set(vals))]
    return ["state", "projection", *sorted(few), *groups, *([STATE_GROUP] if k.states else [])]


def _series(p) -> list[dict]:
    m = p.measurements
    names = sorted(m.newest())
    return [{"name": n, "unit": _series_unit(p, n)} for n in names]


def _pipeline(name: str, k) -> dict:
    """A projection's ``pipeline:``, and ``holds``: its relation naming the projection it takes from (its default
    dashboard row)."""
    w = k.pipeline["waiting"]
    took = (w.get("projection") or w.get("kind")) if w else None
    shown = {"projection": took, **{x: v for x, v in w.items() if x not in ("kind", "projection")}} if w else None
    return {"projection": name, **k.pipeline, "waiting": shown,
            "holds": next((r for r, x in k.relations.items() if took and took in x.kinds), None)}


def _read(p) -> dict:
    spec = getattr(p.model, "spec", None)
    kinds = its.kinds_of(spec)
    items_, moves, types = {}, {}, set()
    for name, k in kinds.items():
        types |= set(k.on)
        finished = list(its.finishes(p.events, spec, name)["finished"])
        # the states its work waits in to be taken (the default dashboard's "waiting"), as the Graph gives them
        moves[name] = {"states": list(k.states), "finished": finished, "queue": finish_of(spec, name, set())["queue"]}
        ix = its._index(p.events, spec, its.asks_transcript([k]))
        if ix is None:
            items_[name] = {"fields": [], "states": list(k.states), "finished": finished, "group_by": ["state", "projection"]}
            continue
        items_[name] = {"fields": [{"name": f["field"], "unit": f["unit"]} for f in numberreads.fields_of(ix).get(name, ())],
                        "states": list(k.states), "finished": finished, "group_by": _groupable(ix, k)}
    sources = {"items": {"projections": items_}, "moves": {"projections": moves}, "counts": {"projections": list(kinds)},
               "series": {"series": _series(p)}, "events": {"types": sorted(types)},
               "frequency": {"needs": ["input", "output"], "segments": {"default": SEGMENTS, "min": 2, "max": MOST_SEGMENTS},
                             "goals": [g for g, x in (getattr(spec, "goals", None) or {}).items() if x.process]}}
    for name, got in sources.items():
        got["x"] = list(X_OF[name])
        got["ohlc"] = name in OHLC_SOURCES
    return {"sources": sources, "x_types": list(X_TYPES),
            "pipelines": [_pipeline(n, k) for n, k in kinds.items() if k.pipeline],     # (SPEC §5a, Stages)
            "aggregations": list(AGGS), "transforms": list(TRANSFORMS), "rate_per": list(RATE_PER),
            "rate_units": dict(transforms.SHORT)}


def fields(live, p, reader: bool = False) -> dict:
    """``datasources``: ergostat's two sources, ``promql`` and ``sql``, always both, each saying whether it can be asked
    now and, when not, why (datasources.listed), the SQL one its ``views`` and their columns (what its editor
    completes); ``reader``: anyone under a public name, who may ask neither (SPEC
    §4e). The built-in kinds under ``sources`` are query generators over them (sources.py)."""
    key = ("query-fields", int(time.time() // KEEP), getattr(live, "mtime", None))
    got = live.cached(key)
    if got is None:
        got = _read(p)
        live.keep(key, got)
    listed = datasources.listed(getattr(p, "measurements", None), p, reader)
    spec = getattr(p.model, "spec", None)
    for d in listed:                    # the views the SQL source reads and their columns: what its editor completes
        if d["name"] == datasources.SQL and d["available"] and spec is not None:
            from ..datasources._itemviews import views
            d["views"] = {v: list(cs) for v, cs in views(spec).items()}
    return {**got, "datasources": listed}
