"""A query as asked: decoded, checked and bounded, or refused with words naming what is wrong."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from ..durations import parse_duration
from ..spec.item_sets import BadSet

SOURCES = ("items", "moves", "counts", "series", "events")
AGGS = ("count", "sum", "avg", "min", "max", "last", "p50", "p90", "p95", "p99")
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
        "measure", "state", "series", "type", "first_only", "include_open"}
DEFAULT_AGG = {"items": "sum", "moves": "count", "counts": "last", "series": "avg", "events": "count"}


class BadQuery(BadSet):
    """A query that cannot be asked: answered 400 with these words."""


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
    first_only: bool = False        # entries: only each item's first entry to the state, never a return to it
    include_open: bool = False      # time_in_state: also the items in the state now, at their age so far


@dataclass(frozen=True)
class Refused:
    """A query that cannot be asked: it answers with these words, and the others still answer."""
    id: str
    error: str


@dataclass(frozen=True)
class Asked:
    since: float                    # the window, in seconds back from ``until``
    until: float | None
    points: int
    queries: tuple[Query | Refused, ...]


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


def _query(d, i: int) -> Query:
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
    default = "p50" if measure == "time_in_state" else DEFAULT_AGG[source]
    q = Query(id=str(id_), source=source, agg=_word(d, "agg", AGGS, default, who),
              transform=_word(d, "transform", TRANSFORMS, "none", who), kind=_text(d, "kind", who),
              field=_text(d, "field", who), where=_where(d, who), group_by=_text(d, "group_by", who),
              rate_per=_word(d, "rate_per", tuple(RATE_PER), None, who), bucket=_bucket(d, who),
              window=_window(d, who), measure=measure,
              state=None if d.get("state") is None else _texts(d["state"], f"{who}: state"),
              series=_text(d, "series", who), type=_text(d, "type", who), first_only=_flag(d, "first_only", "entries", measure, who),
              include_open=_flag(d, "include_open", "time_in_state", measure, who))
    if source == "items" and not q.field:
        raise BadQuery(f"{who}: field is missing (a numeric field of the kind)")
    if source == "series" and not q.series:
        raise BadQuery(f"{who}: series is missing (a metric's name)")
    return q


def _flag(d: dict, key: str, needs: str, measure: str | None, who: str) -> bool:
    v = d.get(key, False)
    if not isinstance(v, bool):
        raise BadQuery(f"{who}: {key} must be true or false")
    if v and measure != needs:
        raise BadQuery(f"{who}: {key} is for the measure {needs}")
    return v


def _window(d: dict, who: str) -> int:
    v = d.get("window", 5)
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MOST_AVERAGED:
        raise BadQuery(f"{who}: window must be a whole number of buckets, 1 to {MOST_AVERAGED}")
    return v


def _id_of(x, i: int) -> str:
    """The id its answer goes under, even for a query that is not well formed."""
    v = x.get("id", i) if isinstance(x, dict) else i
    return str(v) if isinstance(v, str | int) and not isinstance(v, bool) and len(str(v)) <= 64 else str(i)


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
    """The request, checked: one that is not well formed is refused whole, a query that is not answers with why."""
    until = d.get("until")
    if until is not None and (isinstance(until, bool) or not isinstance(until, int | float) or not 0 < until < 1e11):
        raise BadQuery("query: until must be a Unix time, or null for now")
    points = d.get("points", POINTS)
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= MOST_POINTS:
        raise BadQuery(f"query: points must be a whole number from 2 to {MOST_POINTS}")
    qs = d.get("queries")
    if not isinstance(qs, list) or not qs:
        raise BadQuery("query: queries must be a list of at least one")
    got: list[Query | Refused] = []
    seen: set[str] = set()
    for i, x in enumerate(qs):
        id_ = _id_of(x, i)
        if i >= MOST_QUERIES:
            got.append(Refused(id_, f"query {id_}: not answered, past the {MOST_QUERIES} queries one request may ask"))
        elif id_ in seen:
            got.append(Refused(id_, f"query {id_}: two queries have the same id"))
        else:
            try:
                got.append(_query(x, i))
            except BadQuery as e:
                got.append(Refused(id_, str(e)))
        seen.add(id_)
    got = tuple(got)
    return Asked(_since(d.get("since")), None if until is None else float(until), points, got)
