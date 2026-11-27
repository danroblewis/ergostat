"""The projection workbench's API (SPEC §5a, *The workbench*): ``POST /api/events/query`` (the query engine,
``eventquery.py``), ``POST /api/events/kinds`` (the kinds of event a query's result holds, suggested),
``POST /api/projections/review`` (a draft held against its events, ``spec/workbench.py``), ``POST /api/projections/try``
(the try's report, ``spec/trying.py``), ``POST /api/projections/fold`` (events folded by a draft: one sample's record), ``POST /api/projections/save`` (the owner's Save of its definition, written and
accepted at once, its changed parts dated: ``numbers/display.save_projection``), and ``GET /api/events/shape`` (the
stream's shape)."""

from __future__ import annotations

import json
import time

from ..durations import DurationError, parse_duration
from ..numbers import proposals as pr
from ..spec import trying
from ..webaccess import who

BODY_MOST = 8 * 1024 * 1024        # a try may carry its own events


def moment(v, now: float | None = None) -> float | None:
    """A time asked for: seconds since the epoch, or a span back from now (``7d``)."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    try:
        return (now or time.time()) - parse_duration(str(v), "since")
    except DurationError as e:
        raise trying.TryError(str(e)) from None


def tried(p, ask: dict, keep: bool = True) -> dict:
    """The try's report from its JSON body (the page's, the CLI's and the MCP tool's)."""
    if not isinstance(ask, dict):
        raise trying.TryError("a try is {name, yaml, since?, until?, events?, expected?, item?, refused?, limit?}")
    text = ask.get("yaml")
    if not isinstance(text, str):
        raise trying.TryError("yaml: the projection's body (query:, key:, fields:, events:...) as text")
    evs = ask.get("events")
    if evs is not None and not isinstance(evs, list):
        raise trying.TryError("events: a list of events (or leave it out to read the record)")
    lim = ask.get("limit")
    return trying.run(p, ask.get("name"), text, since=moment(ask.get("since")), until=moment(ask.get("until")),
                      events=evs, expected=ask.get("expected"), item=ask.get("item") or None,
                      refused=ask.get("refused") or None, limit=int(lim) if isinstance(lim, (int, float)) else None,
                      system=str(ask.get("system") or ""), keep=keep)


def post(live, path: str, body: bytes, window: float) -> tuple[int, dict]:
    p = live.get()
    if getattr(p.model, "spec", None) is None:
        return 400, {"error": "the model is an ergostat.toml: projections are declared in ergostat.yaml"}
    try:
        ask = json.loads(body or b"null")
    except (ValueError, RecursionError):
        return 400, {"error": "the body is not JSON"}
    if path == "projections/try":
        try:
            return 200, tried(p, ask)
        except trying.TryError as e:
            return 400, {"error": str(e)}
    if path in ("events/query", "events/kinds", "projections/review", "projections/fold"):
        from ..eventquery import QueryError
        from ..eventquery import run as query
        from ..spec import workbench
        try:
            if isinstance(ask, dict):
                ask = {**ask, **{k: moment(ask.get(k)) for k in ("since", "until") if ask.get(k) not in (None, "")}}
            if path == "events/query":
                return 200, query(p.events, ask)
            if path == "projections/fold":
                return 200, workbench.folded(p, ask)
            return 200, (workbench.suggest(p, ask) if path == "events/kinds" else workbench.review(p, ask))
        except (trying.TryError, QueryError) as e:
            return 400, {"error": str(e)}
    from ..numbers import display
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=None)
    snap = {"at": time.time(), "window": window, "starts": oldest}
    try:
        got = display.save_projection(p, ask, snap, by=who())
    except pr.ProposalError as e:
        return 409, {"error": str(e)}
    live.reloaded()
    return 200, got


def shape(p, one) -> dict:
    lim = one("limit")
    return trying.stream_shape(p, one("type") or None, moment(one("since")), int(lim) if lim else None, one("draft"))
