"""The ``analysis`` source (SPEC §4e, *Analysis*): a call over other queries of the same request, answered on the
server. Its language is small and closed: a call's name, the ids of the queries it reads, then ``key=value`` options,
as in ``raw(A, points=2000)``. Text that does not parse is refused with its column; so is an unknown call or option, and
a reference to a missing id, to itself, to another analysis query or to a query that was not answered.

``raw(A)``, A an ergostat ``series`` query: A's readings, never its roll-ups, on one uniform grid whose step is their
median spacing, coarsened only to stay within ``points``. A hole longer than ``GAP_SAMPLES`` spacings stays empty and is
listed in ``gaps`` as ``[from, to]``; a shorter one is a straight line. Where only roll-ups cover the window it is
refused (``only-rollups``). A a data source's query: asked again at the finest step the point bound allows, said to be
not raw (``not-raw``): its range windows still smooth it."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import datasources
from ..datasources import SourceError
from .buckets import Grid
from .frequency import GAP_SAMPLES, _filled
from .parse import ANALYSIS, Query, SourceQuery

CALLS = {"raw": ("points",)}            # a call: its options (each reads one query)
RAW_POINTS = 5000                      # the most points a raw answer holds
LEAST_POINTS = 16
READINGS_MOST = 500_000                # readings one raw answer reads
SCRAPE_READINGS = 2_000                # the newest readings an answer's scrape interval is read from
MOST_GAPS = 200
_TOKEN = re.compile(r"\s*(?:([A-Za-z0-9_.\-]+)|(\S))")
_IN = "from samples where series = ? and time >= ? and time <= ?"


@dataclass(frozen=True)
class Call:
    name: str
    refs: tuple[str, ...]
    opts: dict                          # option: (its text, its column)


def of(q) -> bool:
    return isinstance(q, SourceQuery) and q.source == ANALYSIS


def _bad(words: str, at: int | None = None, kind: str = "refused", code: str | None = None) -> SourceError:
    return SourceError(kind, words, (1, at) if at else None, code)


def call(text: str) -> Call:
    """The call ``text`` says, or SourceError naming what is wrong and its column (from 1)."""
    toks = [(m[2] or "word", m[1] or m[2], m.start(1 if m[1] else 2) + 1) for m in _TOKEN.finditer(text)]
    toks.append(("end", "", len(text) + 1))
    at = 0

    def take(kind: str, what: str) -> tuple[str, int]:
        nonlocal at
        k, v, col = toks[at]
        if k != kind:
            raise _bad(f"column {col}: {what} was expected, not {repr(v) if v else 'the end'}", col)
        at += 1
        return v, col

    name, col = take("word", "a call's name (raw)")
    if name not in CALLS:
        raise _bad(f"column {col}: {name!r} is not a call; the calls are {', '.join(CALLS)}", col)
    take("(", "(")
    refs, opts = [], {}
    while toks[at][0] != ")":
        if refs or opts:
            take(",", ", or )")
        v, col = take("word", "a query's id or an option")
        if toks[at][0] == "=":
            at += 1
            if v not in CALLS[name] or v in opts:
                raise _bad(f"column {col}: {v!r} is not an option of {name} (or is given twice); its options are "
                           f"{', '.join(CALLS[name])}", col)
            opts[v] = take("word", f"a value of {v}")
        elif opts:
            raise _bad(f"column {col}: the query id {v!r} comes after an option; the ids come first", col)
        else:
            refs.append(v)
    take(")", ")")
    take("end", "the end of the text")
    if len(refs) != 1:
        raise _bad(f"{name} reads one query, by its id; it was given {len(refs)}")
    return Call(name, tuple(refs), opts)


def referenced(c: Call, q: SourceQuery, queries: dict, answered: dict):
    """The query ``c`` reads: one of data in this request, answered."""
    ref = c.refs[0]
    if ref == q.id:
        raise _bad(f"{c.name}({ref}) reads itself; it reads another query of this request")
    if ref not in queries:
        raise _bad(f"there is no query {ref!r} in this request")
    if of(queries[ref]):
        raise _bad(f"query {ref!r} is itself an analysis; {c.name} reads a query of data")
    if (got := answered.get(ref)) is None or got.get("error"):      # a failed answer is never read as an empty one
        raise _bad(f"query {ref!r} was not answered, so there is nothing to read ({(got or {}).get('error')})")
    return queries[ref]


def _points(c: Call) -> int:
    v, col = c.opts.get("points", (str(RAW_POINTS), None))
    if not v.isdigit() or not LEAST_POINTS <= int(v) <= RAW_POINTS:
        raise _bad(f"column {col}: points is a whole number from {LEAST_POINTS} to {RAW_POINTS}", col)
    return int(v)


def spacing(c, series: str, since: float, until: float, most: int) -> float | None:
    """The median spacing of a series' newest ``most`` raw readings in a window, or None."""
    near = f"select time {_IN} order by time desc limit {int(most)}"
    lag = f"select time - lag(time) over (order by time) d from ({near})"
    n = c.execute(f"select count(*) from ({lag}) where d > 0", (series, since, until)).fetchone()[0]
    got = c.execute(f"select d from ({lag}) where d > 0 order by d limit 1 offset ?", (series, since, until, (n - 1) // 2))
    return (got.fetchone() or (None,))[0] if n else None


def scrape(m, series: str, since: float, until: float) -> float | None:
    """A series' scrape interval in a window (of its newest ``SCRAPE_READINGS``: every answer of a series pays it),
    where its raw readings are kept there; None where it is not known."""
    if not hasattr(m, "_sources"):
        return None
    with m._c() as c:
        return spacing(c, series, since, until, SCRAPE_READINGS)


def scrapes(m, qs, since: float, until: float) -> dict:
    """``{"scrape_s": ...}`` of an answer built from the readings of the ``series`` queries among ``qs``: the coarsest
    of their scrapes, None if any is unknown; ``{}`` where none is a series (not sampled)."""
    got = [scrape(m, q.series, since, until) for q in qs if getattr(q, "source", None) == "series"]
    return {"scrape_s": None if None in got else max(got)} if got else {}


def raw(m, q: Query, since: float, until: float, c: Call) -> dict:
    if q.source != "series":
        raise _bad(f"raw reads a series query or a data source's query; query {q.id!r} reads {q.source}")
    if q.transform != "none":
        raise _bad(f"raw reads readings as they are; query {q.id!r} has the transform {q.transform}")
    most = _points(c)
    if not hasattr(m, "_sources"):
        raise _bad("this metrics store keeps no raw readings ergostat can tell from its roll-ups", kind="unknown")
    span = (q.series, since, until)
    with m._c() as db:
        n = db.execute(f"select count(*) {_IN}", span).fetchone()[0]
        if n > READINGS_MOST:
            raise _bad(f"{n} readings, more than the {READINGS_MOST} one raw answer reads", kind="limit")
        if n < 2 and db.execute("select count(*) from tiers where series = ? and t <= ? and t + every > ?",
                                (q.series, until, since)).fetchone()[0]:
            raise _bad(f"series {q.series!r} has only roll-ups in this window, and roll-ups are not raw", code="only-rollups")
        each = spacing(db, *span, READINGS_MOST) if n >= 2 else None
        if each is None:
            raise _bad(f"series {q.series!r} has {n} readings in this window at distinct times; raw needs two",
                       kind="unknown")
        step = max(each, (until - since) / (most - 2))
        start = math.floor(since / step) * step
        g = Grid(since, until, step, start, max(1, math.ceil((until - start) / step)))
        values: list = [None] * g.n
        for b, v in db.execute(f"select min(max(cast((time - ?) / ? as integer), 0), ?), avg(value) {_IN} group by 1",
                               (start, step, g.n - 1, *span)):
            values[b] = v
        gaps = db.execute(f"select a, t from (select lag(time) over (order by time) a, time t {_IN}) where t - a > ? "
                          f"order by t limit ?", (*span, GAP_SAMPLES * each, MOST_GAPS + 1)).fetchall()
        parts = m._sources(db, q.series, since, until)
    said = [("partial", f"from {lo:.0f} to {hi:.0f} only roll-ups are kept: left empty, never read as raw")
            for e, lo, hi in parts if e > 0]
    said += [("partial", f"more than {MOST_GAPS} gaps: the first {MOST_GAPS} are listed")] if len(gaps) > MOST_GAPS else []
    said += [("partial", f"{n} readings {each:g} s apart are averaged into steps of {step:g} s, "
                         f"to stay within {most} points")] if step > each else []
    return {"times": g.times, "step": step, "series": [{"name": q.series, "values": _filled(values, GAP_SAMPLES * each / step)}],
            "unit": "", "capped": 0, "read_log": False, "gaps": [list(x) for x in gaps[:MOST_GAPS]], "scrape_s": each,
            "warnings": said}


def reasked(got: dict, ref: SourceQuery) -> dict:
    """A data source's query asked again at its finest step: never said to be raw."""
    ws = got.get("range_windows_s") or []
    says = (f"query {ref.id!r} is asked again at a step of {got.get('step'):g} s, the finest {datasources.MOST_POINTS} "
            f"points allow; " + (f"its range windows ({', '.join(f'{w:g} s' for w in ws)}) still smooth it, so "
                                 if ws else "") + "this is the source's answer, not its raw readings")
    return {**got, "warnings": [*got.get("warnings", ()), ("not-raw", says)]}
