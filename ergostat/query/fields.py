"""``GET /api/query/fields``: what can be charted, from the model and the indexes, without reading the event log."""

from __future__ import annotations

import time

from ..spec import codec, numberreads
from ..spec import items as its
from . import transforms
from .axes import X_OF, X_TYPES
from .labels import word
from .parse import AGGS, MOST_SEGMENTS, RATE_PER, SEGMENTS, TRANSFORMS
from .sources import OHLC_SOURCES, _series_unit

SAMPLE = 200                # the latest items a kind's low-cardinality fields are told from
FEW = 12                    # the most distinct values a field to group by may have
LABEL_MOST = 40             # characters: a longer value is prose, not a category
KEEP = 30.0                 # seconds an answer is kept


def _groupable(ix, k) -> list[str]:
    """``state``, ``kind``, and the fields its latest items hold few distinct texts in."""
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
    return ["state", "kind", *sorted(few)]


def _series(p) -> list[dict]:
    m = p.measurements
    names = sorted(m.newest()) if hasattr(m, "newest") else [s["series"] for s in m.series()]
    return [{"name": n, "unit": _series_unit(p, n)} for n in names]


def _read(p) -> dict:
    spec = getattr(p.model, "spec", None)
    kinds = its.kinds_of(spec)
    items_, moves, types = {}, {}, set()
    for name, k in kinds.items():
        types |= set(k.on)
        finished = list(its.finishes(p.events, spec, name)["finished"])
        moves[name] = {"states": list(k.states), "finished": finished}
        ix = its._index(p.events, spec, its.asks_transcript([k]))
        if ix is None:
            items_[name] = {"fields": [], "states": list(k.states), "finished": finished, "group_by": ["state", "kind"]}
            continue
        items_[name] = {"fields": [{"name": f["field"], "unit": f["unit"]} for f in numberreads.fields_of(ix).get(name, ())],
                        "states": list(k.states), "finished": finished, "group_by": _groupable(ix, k)}
    sources = {"items": {"kinds": items_}, "moves": {"kinds": moves}, "counts": {"kinds": list(kinds)},
               "series": {"series": _series(p)}, "events": {"types": sorted(types)},
               "frequency": {"needs": ["input", "output"], "segments": {"default": SEGMENTS, "min": 2, "max": MOST_SEGMENTS},
                             "goals": [g for g, x in (getattr(spec, "goals", None) or {}).items() if x.process]}}
    for name, got in sources.items():
        got["x"] = list(X_OF[name])
        got["ohlc"] = name in OHLC_SOURCES
    return {"sources": sources, "x_types": list(X_TYPES),
            "aggregations": list(AGGS), "transforms": list(TRANSFORMS), "rate_per": list(RATE_PER),
            "rate_units": dict(transforms.SHORT)}


def fields(live, p) -> dict:
    key = ("query-fields", int(time.time() // KEEP), getattr(live, "mtime", None))
    got = live.cached(key)
    if got is None:
        got = _read(p)
        live.keep(key, got)
    return got
