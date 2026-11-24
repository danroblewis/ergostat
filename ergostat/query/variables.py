"""``GET /api/query/values?q=...``: the values a dashboard variable written as a query may take (SPEC §4e, *Variables*).
``q`` is base64url of ``{"source": name, "text": "label_values(selector, label)", "since": seconds, "until": time,
"vars": {...}}``; the answer is ``{"values": [...]}`` or ``{"error", "error_kind"}``. Never kept; a reader (anyone under a
public name) is refused it, as every data source query."""

from __future__ import annotations

import time

from .. import datasources
from .engine import READER_REFUSED
from .parse import MOST_WINDOW, BadQuery, decode, source_vars


def values(p, raw: str | None, reader: bool = False) -> dict:
    d = decode(raw)
    if extra := sorted(set(d) - {"source", "text", "since", "until", "vars"}):
        raise BadQuery(f"values: {extra[0]!r} is not a key (source, text, since, until and vars)")
    source, text, since, until = d.get("source"), d.get("text"), d.get("since", 86400), d.get("until")
    if not isinstance(source, str) or not source or not isinstance(text, str):
        raise BadQuery("values: source (a name under sources:) and text (label_values(...)) are needed")
    num = lambda v: isinstance(v, int | float) and not isinstance(v, bool) and v == v and abs(v) < 1e12  # noqa: E731
    if not num(since) or not 0 < since <= MOST_WINDOW or (until is not None and not num(until)):
        raise BadQuery(f"values: since must be seconds, more than 0 and at most {int(MOST_WINDOW)}; until a time")
    given = dict((k, list(v)) for k, v in source_vars(d.get("vars"), "values"))
    if reader:
        return {"error": f"{source}: {READER_REFUSED}", "error_kind": "refused"}
    end = time.time() if until is None else float(until)
    try:
        return {"values": datasources.values(getattr(p.model, "spec", None), source, text, end - since, end,
                                             datasources.MOST_SECONDS, given,
                                             store=getattr(p, "measurements", None))}
    except datasources.SourceError as e:
        return {"error": f"{source}: {e}", "error_kind": e.kind}
    except Exception as e:                            # (its type only: the words may hold the source's address)
        return {"error": f"{source}: could not be read ({type(e).__name__})", "error_kind": "unknown"}
