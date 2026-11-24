"""The ``analysis`` source (SPEC §4e, *Analysis*): a call over other queries of the same request, answered on the
server. Its language is small and closed: a call's name, the ids of the queries it reads, then ``key=value`` options,
as in ``raw(A, points=2000)``. Text that does not parse is refused with its column; so is an unknown call or option, and
a reference to a missing id, to itself, to another analysis query or to a query that was not answered.

``raw(A)``, A an ergostat ``series`` query: A's readings, never its roll-ups, on one uniform grid whose step is their
median spacing, coarsened only to stay within ``points``. A hole longer than ``GAP_SAMPLES`` spacings stays empty and is
listed in ``gaps`` as ``[from, to]``; a shorter one is a straight line. Where only roll-ups cover the window it is
refused (``only-rollups``). A a data source's query: asked again at the finest step the point bound allows, said to be
not raw (``not-raw``): its range windows still smooth it.

``pair(A, B)``, ``psd(A, ...)``, ``spectrogram(A, ...)`` and ``ccf(A, B, ...)`` read their signals only through that
re-read, put on one grid (``called``; the arithmetic is spectra.py's). A spectrum of a data source's answer under range
windows is refused (``windowed``, G1), never made from the windowed values."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import datasources
from ..datasources import SourceError
from . import spectra
from .buckets import Grid
from .frequency import GAP_SAMPLES, MOST_SEGMENTS, SEGMENTS, Refused
from .parse import ANALYSIS, Query, SourceQuery

CALLS = {"raw": ("points",), "pair": (), "psd": ("detrend", "segments"), "spectrogram": ("length", "detrend", "cells"),
         "ccf": ("most_lag",)}         # a call: its options
TWO = ("pair", "ccf")                  # the calls that read two queries; the rest read one
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

    name, col = take("word", f"a call's name ({', '.join(CALLS)})")
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
    if len(refs) != (want := 2 if name in TWO else 1):
        raise _bad(f"{name} reads {'two queries' if want == 2 else 'one query'}, by id; it was given {len(refs)}")
    return Call(name, tuple(refs), opts)


def referenced(c: Call, q: SourceQuery, queries: dict, answered: dict) -> list:
    """The queries ``c`` reads: each one of data in this request, answered."""
    for ref in c.refs:
        if ref == q.id:
            raise _bad(f"{c.name}({ref}) reads itself; it reads another query of this request")
        if ref not in queries:
            raise _bad(f"there is no query {ref!r} in this request")
        if of(queries[ref]):
            raise _bad(f"query {ref!r} is itself an analysis; {c.name} reads a query of data")
        if (got := answered.get(ref)) is None or got.get("error"):      # a failed answer is never read as an empty one
            raise _bad(f"query {ref!r} was not answered, so there is nothing to read ({(got or {}).get('error')})")
    return [queries[ref] for ref in c.refs]


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


def _lines(values: list, cut: set) -> list:
    """Straight lines between the readings' buckets, except from a bucket in ``cut``, where a hole of the gap mask
    starts: the mask and the fill are one rule, so a listed hole is never drawn over."""
    out = list(values)
    at = [i for i, v in enumerate(values) if v is not None]
    for a, b in zip(at, at[1:], strict=False):
        for i in range(a + 1, b) if a not in cut else ():
            out[i] = values[a] + (values[b] - values[a]) * (i - a) / (b - a)
    return out


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
                          f"order by t", (*span, GAP_SAMPLES * each)).fetchall()
        parts = m._sources(db, q.series, since, until)
    said = [("partial", f"from {lo:.0f} to {hi:.0f} only roll-ups are kept: left empty, never read as raw")
            for e, lo, hi in parts if e > 0]
    said += [("partial", f"more than {MOST_GAPS} gaps: the first {MOST_GAPS} are listed")] if len(gaps) > MOST_GAPS else []
    said += [("partial", f"{n} readings {each:g} s apart are averaged into steps of {step:g} s, "
                         f"to stay within {most} points")] if step > each else []
    at = lambda t: min(max(int((t - start) / step), 0), g.n - 1)  # noqa: E731 - the bucket of a time, as the SQL above
    cut = {at(a) for a, t in gaps if at(t) > at(a)}               # the bucket each hole of the mask starts in
    return {"times": g.times, "step": step, "series": [{"name": q.series, "values": _lines(values, cut)}],
            "unit": "", "capped": 0, "read_log": False, "gaps": [list(x) for x in gaps[:MOST_GAPS]], "scrape_s": each,
            "warnings": said}


def reasked(got: dict, ref: SourceQuery) -> dict:
    """A data source's query asked again at its finest step: never said to be raw."""
    ws = got.get("range_windows_s") or []
    says = (f"query {ref.id!r} is asked again at a step of {got.get('step'):g} s, the finest {datasources.MOST_POINTS} "
            f"points allow; " + (f"its range windows ({', '.join(f'{w:g} s' for w in ws)}) still smooth it, so "
                                 if ws else "") + "this is the source's answer, not its raw readings")
    return {**got, "warnings": [*got.get("warnings", ()), ("not-raw", says)]}


def _count(c: Call, key: str, default: int, most: int, least: int = 1) -> int:
    v, col = c.opts.get(key, (str(default), None))
    if not (v.isdigit() and len(v) <= 6 and least <= int(v) <= most):
        raise _bad(f"column {col}: {key} is a whole number from {least} to {most}", col)
    return int(v)


def _seconds(c: Call, key: str) -> float | None:
    """A duration option (``90``, ``90s``, ``10m``, ``2h``), in seconds; its bound in samples is the call's to hold."""
    if key not in c.opts:
        return None
    (v, col), m = c.opts[key], re.fullmatch(r"(\d{1,9}(?:\.\d{1,9})?)(s|m|h|d)?", c.opts[key][0])
    if not m or not float(m[1]) > 0:
        raise _bad(f"column {col}: {key} is a duration above zero, such as 90s, 10m or 2h; not {v!r}", col)
    return float(m[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m[2] or "s"]


def _signal(got: dict, ref, name: str) -> tuple[list, list, float]:
    s = got.get("series") or []
    if got.get("shape", "series") != "series" or len(s) != 1 or not got.get("times") or s[0].get("role"):
        raise _bad(f"{name} reads one signal in time; query {ref.id!r} answers {len(s)} series (aggregate it to one)")
    return got["times"], s[0]["values"], got["step"]


def _onto(times: list, values: list, start: float, step: float, n: int) -> list:
    """A signal on the grid ``start + i * step``: each bucket the mean of its values, empty where it holds none."""
    sums, counts = [0.0] * n, [0] * n
    for t, v in zip(times, values, strict=True):
        if v is not None and 0 <= (i := int(math.floor((t - start) / step + 1e-9))) < n:
            sums[i] += v
            counts[i] += 1
    return [x / k if k else None for x, k in zip(sums, counts, strict=True)]


def called(c: Call, got: list[dict], refs: list) -> dict:
    """``pair``, ``psd``, ``spectrogram`` or ``ccf`` (spectra.py) over the raw re-reads ``got`` of ``refs``, on one grid
    (the coarsest of their steps); each refusal of the record is the call's, in words (``unanalysable``)."""
    ids = [r.id for r in refs]
    wins = [g.get("range_windows_s", []) for g in got]
    if c.name in ("psd", "spectrogram") and wins[0] != []:
        raise _bad(f"{c.name} reads raw values, and query {ids[0]!r}'s cannot be read: it is a data source's answer "
                   f"under range windows ({', '.join(f'{w:g} s' for w in wins[0] or ()) or 'not read'}), which average "
                   f"away each period W/k (G1), so no spectrum is made from it", code="windowed")
    sigs = [_signal(g, r, c.name) for g, r in zip(got, refs, strict=True)]
    step = max(s for _, _, s in sigs)
    start = math.floor(min(t[0] for t, _, _ in sigs) / step) * step
    n = int((max(t[-1] for t, _, _ in sigs) - start) // step) + 1
    vals = [_onto(t, v, start, step, n) for t, v, _ in sigs]
    times = [start + i * step for i in range(n)]
    said = [w for g in got for w in g.get("warnings") or ()]
    if len(sigs) == 2 and (sigs[0][2] != sigs[1][2] or wins[0] != wins[1]):
        said.append(("mixed-windows", "; ".join(f"{i!r} was read at a step of {s:g} s, range windows "
                                                f"{', '.join(f'{w:g} s' for w in ws) if ws else 'none' if ws == [] else 'not read'}"
                                                for i, (_, _, s), ws in zip(ids, sigs, wins, strict=True))
                      + f": both are put on one grid of {step:g} s, so they are not compared period for period"))
    scrapes = [g.get("scrape_s") for g in got]
    scrape = None if None in scrapes else max(scrapes)
    try:
        if c.name == "pair":
            out = spectra.pair(ids, *vals, times)
        elif c.name == "ccf":
            out = spectra.ccf(ids, *vals, step, _seconds(c, "most_lag"))
        elif (how := c.opts.get("detrend", ("linear", None)))[0] not in spectra.DETRENDS:
            raise _bad(f"column {how[1]}: detrend is one of {', '.join(spectra.DETRENDS)}", how[1])
        elif c.name == "psd":
            out = spectra.psd(ids[0], vals[0], step, scrape, how[0], _count(c, "segments", SEGMENTS, MOST_SEGMENTS))
        else:
            out = spectra.spectrogram(ids[0], vals[0], step, start, scrape, _seconds(c, "length"), how[0],
                                      _count(c, "cells", spectra.MOST_CELLS, spectra.MOST_CELLS))
    except Refused as e:
        raise _bad(f"{c.name}: {e}", code="unanalysable") from None
    ws = None if None in wins else sorted({w for x in wins for w in x})
    return {**out, "step": out.get("sample_seconds", step), "scrape_s": scrape, "range_windows_s": ws, "warnings": said}
