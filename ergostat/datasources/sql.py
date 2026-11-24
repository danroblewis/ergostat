"""The ``sql`` data source (SPEC §4e, *The SQL source*): SQLite's SQL over the stable, read-only views of the asking
project's own items (_itemviews.py), for what PromQL cannot ask: which items, one item against another, exact
medians, cohorts. Its connection is the project's record, so it has no keys::

    sources:
      record:
        type: sql

A query is one SELECT. ``:since``, ``:until`` and ``:step`` are the panel's window (Unix seconds). It may take 10 s or
less (the request's remaining time), answer 5,000 rows and 8 MB, and make values of 16 MB; past any it is stopped and
refused with ``limit``. Anything but a SELECT through the views (a write, ATTACH, PRAGMA, the index's own tables) is
refused with ``refused``.

The answer is typed by its columns: a first column named ``time`` makes series, one a column after it; otherwise the
leading columns that are not all numbers are a table's dims, and the rest its measures, which must be numbers. An answer
of numbers only is named by row (dim ``row``: "1", "2", ...); a number meant as a name is cast to text."""

from __future__ import annotations

import re
import sqlite3
import time

from . import ASKING, SourceError, _frames, _itemviews

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

TYPE = "sql"
KEYS = ()
LANGUAGE = "SQL"
MOST_BYTES = 8 * 2**20          # of the answer's text and blobs (a number counts 8)


def _project():
    p = ASKING.get()
    spec = getattr(getattr(p, "model", None), "spec", None)
    if p is None or spec is None:
        raise SourceError("unknown", "the SQL source reads the asking project's items, and no project asked")
    return p, spec


def _index(p, spec):
    from ..spec.itemindex import index_for
    ix = index_for(p.events, spec, False)
    if ix is None:
        raise SourceError("unknown", "this project's record is kept nowhere on disk, so it has no item index to read")
    return ix


def _refusal(e: sqlite3.Error, why: list, seconds: float) -> SourceError:
    words = str(e)
    if why:
        return SourceError(*why[0])
    if "interrupted" in words:
        return SourceError("limit", f"the query ran past {seconds:g} s and was stopped")
    if "too big" in words:
        return SourceError("limit", f"the query made a value over the {_itemviews.MOST_VALUE // 2**20} MB allowed")
    if "prohibited" in words or "not authorized" in words:
        return SourceError("refused", f"only a SELECT through the views is allowed ({words})")
    return SourceError("refused", words)


def _fetched(cur) -> list[tuple]:
    rows, size = [], 0
    while batch := cur.fetchmany(500):
        rows += batch
        size += sum(len(v) if isinstance(v, str | bytes) else 8 for r in batch for v in r)
        if len(rows) > _frames.MOST_ROWS:
            raise SourceError("limit", f"the query answered more than the {_frames.MOST_ROWS} rows allowed; aggregate it")
        if size > MOST_BYTES:
            raise SourceError("limit", f"the query answered more than the {MOST_BYTES // 2**20} MB allowed")
    return rows


def _number(v) -> bool:
    return v is None or (isinstance(v, int | float) and not isinstance(v, bool))


def _frame(cols: list[str], rows: list[tuple]) -> dict:
    numeric = [all(_number(r[i]) for r in rows) for i in range(len(cols))]
    if cols[0] == "time" and len(cols) > 1 and all(numeric):
        return {"shape": "series", "time": [r[0] for r in rows],
                "series": [{"key": c, "values": [r[i] for r in rows]} for i, c in enumerate(cols) if i]}
    n = next((i for i, x in enumerate(numeric) if x), len(cols))
    if n >= len(cols):
        raise SourceError("refused", "a SQL answer needs a column of numbers (a measure) after its names; "
                                     "count(*) or a median, say")
    if bad := [c for c, x in zip(cols[n:], numeric[n:], strict=True) if not x]:
        raise SourceError("refused", f"column {bad[0]} holds text after a column of numbers: put names first")
    if not n:                                   # numbers only: each row is named by its place
        cols, rows = ["row", *cols], [(str(i + 1), *r) for i, r in enumerate(rows)]
        n = 1
    return {"shape": "table", "dims": [{"name": c, "type": "string"} for c in cols[:n]],
            "measures": [{"name": c} for c in cols[n:]],
            "rows": [["" if v is None and i < n else v for i, v in enumerate(r)] for r in rows]}


def _forecast(p, text: str) -> dict | None:
    """The forecast, when the text names a ``forecast_*`` view: as last worked out, never worked out on this query;
    with none (being worked out, failed, no run finished) the query is refused with why, never answered empty."""
    if not {x.lower() for x in _WORD.findall(text)} & {*_itemviews.FORECAST, *_itemviews.GROUP_FUNCTIONS}:
        return None
    from ..web.eta_api import current
    fc = current(p, p.model)
    if fc is None:
        raise SourceError("unknown", "the forecast is being worked out; ask again shortly")
    if fc.get("none"):
        raise SourceError("unknown", f"no forecast: {fc['none']}")
    return fc


def query(src, text: str, w) -> dict:
    p, spec = _project()
    deadline = time.monotonic() + w.seconds
    ix = _index(p, spec)
    why: list = []
    fc = _forecast(p, text)
    try:
        with _itemviews.opened(ix, spec, deadline, text, why, fc) as (c, _):
            cur = c.execute(text, {"since": w.since, "until": w.until, "step": w.step})
            if cur.description is None:
                raise SourceError("refused", "the text holds no SELECT")
            cols, rows = [d[0] for d in cur.description], _fetched(cur)
    except sqlite3.Error as e:
        raise _refusal(e, why, w.seconds) from None
    return _frame(cols, rows)


def suggest(src, what: str, prefix: str, metric: str, label: str, seconds: float, most: int) -> tuple[list, bool]:
    """Views (``metrics``) and a view's columns (``labels``, every view's when none is named); no values."""
    _, spec = _project()
    every = _itemviews.views(spec)
    if what == "metrics":
        names = list(every)
    elif what == "labels":
        names = list(every.get(metric, ())) if metric else sorted({c for cs in every.values() for c in cs})
    else:
        names = []
    got = [n for n in names if n.startswith(prefix)]
    return got[:most], len(got) > most
