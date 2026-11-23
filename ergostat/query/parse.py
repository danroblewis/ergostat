"""A query as asked: decoded, checked and bounded, or refused with words naming what is wrong."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, replace

from ..durations import parse_duration
from ..spec.item_sets import BadSet

SOURCES = ("items", "moves", "counts", "series", "events", "frequency")
AGGS = ("count", "sum", "avg", "min", "max", "last", "p50", "p90", "p95", "p99", "ohlc")
NO_AGG = "none"            # each point is one item (an X of type field)
TRANSFORMS = ("none", "rate", "delta", "cumulative", "moving_avg")
MEASURES = ("entries", "exits", "time_in_state")
RATE_PER = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}
MOST_ENCODED = 48_000       # characters of ``q`` (an address must stay an address)
MOST_QUERIES = 64           # a page of 24 panels, a few queries each
MOST_POINTS = 1000
POINTS = 120
MOST_WINDOW = 400 * 86400.0
MOST_AVERAGED = 200         # buckets in a moving average
KEYS = {"id", "source", "kind", "field", "where", "group_by", "agg", "transform", "rate_per", "bucket", "window",
        "measure", "state", "series", "type", "x", "input", "output", "segments", "model"}
DEFAULT_AGG = {"items": "sum", "moves": "count", "counts": "last", "series": "avg", "events": "count", "frequency": "avg"}
X_KEYS = {"type", "query", "field", "by", "bins", "size", "color_by"}
X_TYPES = ("time", "query", "field", "category", "bins")
MOST_BINS = 200
BINS = 20
SEGMENTS = 4
MOST_SEGMENTS = 64


class BadQuery(BadSet):
    """A query that cannot be asked: answered 400 with these words."""


@dataclass(frozen=True)
class X:
    """A non-time X axis. ``query``: another query's id in this request, or the query itself."""
    type: str
    query: object = None
    field: str | None = None
    by: str | None = None
    bins: int = BINS
    size: str | None = None
    color_by: str | None = None


@dataclass(frozen=True)
class Query:
    id: str
    source: str
    agg: str
    transform: str = "none"
    kind: str | None = None
    field: str | None = None
    where: tuple = ()               # ((name, (value, ...)), ...)
    group_by: str | None = None
    rate_per: str | None = None
    bucket: float | None = None
    window: int = 5
    measure: str | None = None
    state: tuple | None = None
    series: str | None = None
    type: str | None = None
    x: X | None = None              # None: time
    input: Query | None = None      # frequency: what is put in, what comes out, or a goal's model
    output: Query | None = None
    segments: int = SEGMENTS
    model: str | None = None


@dataclass(frozen=True)
class Asked:
    since: float                    # the window, in seconds back from ``until``
    until: float | None
    points: int
    queries: tuple[Query, ...]


def decode(q: str | None) -> dict:
    """``q``, base64url of JSON (padded or not)."""
    if not q:
        raise BadQuery("query: q is missing (base64url of a JSON object)")
    if len(q) > MOST_ENCODED:
        raise BadQuery(f"query: q is {len(q)} characters, more than the {MOST_ENCODED} allowed")
    try:
        got = json.loads(base64.b64decode(q + "=" * (-len(q) % 4), altchars=b"-_", validate=True))
    except (binascii.Error, ValueError, RecursionError) as e:
        raise BadQuery("query: q is not base64url of JSON") from e
    if not isinstance(got, dict):
        raise BadQuery("query: q must be a JSON object")
    return got


def _word(d: dict, key: str, allowed, default, who: str) -> str:
    v = d.get(key)
    if v is None:
        return default
    if v not in allowed:
        raise BadQuery(f"{who}: {key} {v!r} is not one of {', '.join(allowed)}")
    return v


def _text(d: dict, key: str, who: str) -> str | None:
    v = d.get(key)
    if v is not None and (not isinstance(v, str) or not v or len(v) > 200):
        raise BadQuery(f"{who}: {key} must be a short text")
    return v


def _texts(v, what: str) -> tuple:
    v = [v] if isinstance(v, str | int | float) and not isinstance(v, bool) else v
    if not isinstance(v, list) or not v or len(v) > 64 or not all(isinstance(x, str | int | float) for x in v):
        raise BadQuery(f"{what} must be a value or a list of at most 64")
    return tuple(str(x) for x in v)


def _where(d: dict, who: str) -> tuple:
    w = d.get("where")
    if w is None:
        return ()
    if not isinstance(w, dict) or len(w) > 8:
        raise BadQuery(f"{who}: where must be an object of at most 8 fields")
    return tuple(sorted((str(k), _texts(v, f"{who}: where.{k}")) for k, v in w.items()))


def _bucket(d: dict, who: str) -> float | None:
    v = d.get("bucket")
    if v in (None, "auto"):
        return None
    try:
        got = parse_duration(v) if isinstance(v, str) else float(v)
    except (TypeError, ValueError) as e:
        raise BadQuery(f"{who}: bucket {v!r} is not auto or a duration") from e
    if isinstance(v, bool) or not 1 <= got <= MOST_WINDOW:
        raise BadQuery(f"{who}: bucket {v!r} is not auto or a duration")
    return got


def _x(d: dict, who: str, depth: int) -> X | None:
    v = d.get("x")
    if v is None:
        return None
    if not isinstance(v, dict):
        raise BadQuery(f"{who}: x must be an object with a type")
    if extra := sorted(set(v) - X_KEYS):
        raise BadQuery(f"{who}: x has {extra[0]!r}, which is not an x key")
    ty = _word(v, "type", X_TYPES, None, f"{who}: x")
    if ty is None:
        raise BadQuery(f"{who}: x.type is missing (one of {', '.join(X_TYPES)})")
    if ty == "time":
        return None
    ref = v.get("query")
    if isinstance(ref, dict):
        if depth:
            raise BadQuery(f"{who}: x.query cannot itself hold a query")
        ref = _query({"id": "x", **ref}, 0, depth + 1)
    elif ref is not None and (not isinstance(ref, str | int) or isinstance(ref, bool) or not str(ref) or len(str(ref)) > 64):
        raise BadQuery(f"{who}: x.query must be another query's id, or a query")
    elif ref is not None:
        ref = str(ref)
    bins = v.get("bins", BINS)
    if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= MOST_BINS:
        raise BadQuery(f"{who}: x.bins must be a whole number from 1 to {MOST_BINS}")
    got = X(ty, ref, _text(v, "field", f"{who}: x"), _text(v, "by", f"{who}: x"), bins,
            _text(v, "size", f"{who}: x"), _text(v, "color_by", f"{who}: x"))
    if ty == "query" and got.query is None:
        raise BadQuery(f"{who}: x.query is missing (the id of another query in this request)")
    if ty == "field" and not got.field:
        raise BadQuery(f"{who}: x.field is missing (a numeric field of the kind)")
    if ty == "category" and not got.by:
        raise BadQuery(f"{who}: x.by is missing (state, kind or a low-cardinality field)")
    if ty == "bins" and got.field and got.query is not None:
        raise BadQuery(f"{who}: x takes a field or a query to bin, not both")
    return got


def _frequency(d: dict, q: Query, who: str, depth: int) -> Query:
    if depth:
        raise BadQuery(f"{who}: a frequency response cannot be an input, an output or an X")
    segments = d.get("segments", SEGMENTS)
    if isinstance(segments, bool) or not isinstance(segments, int) or not 2 <= segments <= MOST_SEGMENTS:
        raise BadQuery(f"{who}: segments must be a whole number from 2 to {MOST_SEGMENTS}")
    model = d.get("model")
    if model is not None:
        goal = model.get("goal") if isinstance(model, dict) else None
        if not isinstance(goal, str) or not goal or len(goal) > 200:
            raise BadQuery(f"{who}: model must be {{\"goal\": name}}")
        if d.get("input") is not None or d.get("output") is not None:
            raise BadQuery(f"{who}: a model's response takes no input or output")
        return replace(q, model=goal, segments=segments)
    for side in ("input", "output"):
        if not isinstance(d.get(side), dict):
            raise BadQuery(f"{who}: {side} is missing (a query)")
    return replace(q, input=_query({"id": "input", **d["input"]}, 0, depth + 1),
                   output=_query({"id": "output", **d["output"]}, 0, depth + 1), segments=segments)


def _query(d, i: int, depth: int = 0) -> Query:
    if not isinstance(d, dict):
        raise BadQuery(f"queries[{i}] must be an object")
    id_ = d.get("id", str(i))
    if not isinstance(id_, str | int) or isinstance(id_, bool) or len(str(id_)) > 64:
        raise BadQuery(f"queries[{i}]: id must be a short text")
    who = f"query {id_}"
    if extra := sorted(set(d) - KEYS):
        raise BadQuery(f"{who}: {extra[0]!r} is not a query key")
    source = _word(d, "source", SOURCES, None, who)
    if source is None:
        raise BadQuery(f"{who}: source is missing (one of {', '.join(SOURCES)})")
    measure = _word(d, "measure", MEASURES, None, who)
    if source == "moves" and measure is None:
        raise BadQuery(f"{who}: measure is missing (one of {', '.join(MEASURES)})")
    x = _x(d, who, depth)
    default = "p50" if measure == "time_in_state" else DEFAULT_AGG[source]
    default = NO_AGG if x and x.type == "field" else "count" if x and x.type == "bins" else default
    agg = _word(d, "agg", (*AGGS, NO_AGG), default, who)
    if agg == NO_AGG and not (x and x.type == "field"):
        raise BadQuery(f"{who}: agg 'none' is only for an x of type field, where each point is one item")
    q = Query(id=str(id_), source=source, agg=agg, x=x,
              transform=_word(d, "transform", TRANSFORMS, "none", who), kind=_text(d, "kind", who),
              field=_text(d, "field", who), where=_where(d, who), group_by=_text(d, "group_by", who),
              rate_per=_word(d, "rate_per", tuple(RATE_PER), None, who), bucket=_bucket(d, who),
              window=_window(d, who), measure=measure,
              state=None if d.get("state") is None else _texts(d["state"], f"{who}: state"),
              series=_text(d, "series", who), type=_text(d, "type", who))
    if source == "frequency":
        return _frequency(d, q, who, depth)
    if source == "items" and not q.field and x and x.type == "bins" and x.field:
        q = replace(q, field=x.field)
    if source == "items" and not q.field:
        raise BadQuery(f"{who}: field is missing (a numeric field of the kind)")
    if source == "series" and not q.series:
        raise BadQuery(f"{who}: series is missing (a metric's name)")
    return q


def _window(d: dict, who: str) -> int:
    v = d.get("window", 5)
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MOST_AVERAGED:
        raise BadQuery(f"{who}: window must be a whole number of buckets, 1 to {MOST_AVERAGED}")
    return v


def _since(v) -> float:
    if v is None:
        return 86400.0
    try:
        got = parse_duration(v) if isinstance(v, str) else float(v)
    except (TypeError, ValueError) as e:
        raise BadQuery(f"query: since {v!r} is not a duration") from e
    if isinstance(v, bool) or not 1 <= got <= MOST_WINDOW:
        raise BadQuery(f"query: since {v!r} must be between 1 second and {int(MOST_WINDOW // 86400)} days")
    return got


def parse(d: dict) -> Asked:
    """The request, checked; a request or query that is not well formed is refused whole."""
    until = d.get("until")
    if until is not None and (isinstance(until, bool) or not isinstance(until, int | float) or not 0 < until < 1e11):
        raise BadQuery("query: until must be a Unix time, or null for now")
    points = d.get("points", POINTS)
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= MOST_POINTS:
        raise BadQuery(f"query: points must be a whole number from 2 to {MOST_POINTS}")
    qs = d.get("queries")
    if not isinstance(qs, list) or not qs:
        raise BadQuery("query: queries must be a list of at least one")
    if len(qs) > MOST_QUERIES:
        raise BadQuery(f"query: {len(qs)} queries, more than the {MOST_QUERIES} allowed")
    got = tuple(_query(x, i) for i, x in enumerate(qs))
    ids = [q.id for q in got]
    if len(set(ids)) != len(ids):
        raise BadQuery("query: two queries have the same id")
    return Asked(_since(d.get("since")), None if until is None else float(until), points, got)
