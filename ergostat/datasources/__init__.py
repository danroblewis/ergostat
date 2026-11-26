"""Ergostat's two data sources (SPEC §4e, *Data sources*; NOTES.md, 2026-11-25, the owner's decision): ``promql``, every
metric, recorded in VictoriaMetrics (``promql.py``), and ``sql``, all item data, projected into SQLite (the item views:
``sql.py``, ``_itemviews.py``). There are no others, and none is declared: everything that is not an external system is
stored in one of the two, and every built-in shortcut (item fields, item moves, items per state, events, metric series,
a frequency response) is a query generator that writes a PromQL or SQL query and asks it of one of them
(query/sources.py), never a source of its own. Sensors that read external systems (a ``sources:`` entry of type
``prometheus``, ``command`` or ``ergostat``) are sensors, not data sources: a panel never asks them.

A panel query is ``{"source": "promql" | "sql", "text": ...}``; the answer has the shape of every chart's (``times``,
``step``, ``series``). Each source's module offers ``query(source, text, window)``, which returns ``[(name, [(time,
value), ...]), ...]`` or a typed frame (series with roles, a table or points: _frames.py), and may offer ``suggest``
(the names an editor completes) and ``values`` (a dashboard variable's ``label_values``). ``listed`` names both,
always, each with whether it can be asked now and, when not, why. Every query is bounded here, whatever its source: its
text, its window, its points and its series, and it is refused with words naming the bound it is over."""

from __future__ import annotations

import math
import re
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from . import _frames, _lint

MOST_TEXT = 4000            # characters of a query's text
MOST_SERIES = 50            # series one query may answer with
MOST_POINTS = 1000          # buckets in a window
MOST_WINDOW = 400 * 86400.0
MOST_SECONDS = 10.0         # the longest one query may take to answer
MOST_VALUES = 200           # values a variable's query may list
MOST_VALUE = 200            # characters of one value
_LABEL_VALUES = re.compile(r"\s*label_values\(\s*(?:(.+)\s*,\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\Z", re.S)
MOST_SUGGESTIONS = 100      # names one suggestion answers with
SUGGEST_SECONDS = 3.0
SUGGESTED = ("metrics", "labels", "values")
PROMQL, SQL = "promql", "sql"
NAMES = (PROMQL, SQL)       # the two sources, in the order they are listed
OLD_NAMES = {"ergostat": PROMQL}   # a saved panel's name for the built-in PromQL source, before it was named promql
CHECKED_EVERY = 5.0         # seconds whether VictoriaMetrics answers is kept, for the listing
READER = "a data source is not asked for anyone under a public name (web: open: read); the owner or a login may ask"
_NAME = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]{0,199}")     # a metric's or a label's name, as a suggestion takes it


class SourceError(Exception):
    """A query that is not answered, and why: ``kind`` is ``limit``, ``unreachable``, ``refused`` or ``unknown``."""

    def __init__(self, kind: str, words: str, at: tuple[int, int] | None = None, code: str | None = None):
        super().__init__(words)
        self.kind = kind
        self.at = at            # (line, column), each from 1: where in the text the source said it is wrong
        self.code = code        # the verdict's reason (query/verdicts.py), when it is not the kind's own


@dataclass(frozen=True)
class Window:
    """What a source is asked for: ``points`` values, one at each of ``start + i * step``, within [since, until]."""
    since: float
    until: float
    start: float
    step: float
    points: int
    seconds: float          # how long it may take
    project: object = field(default=None, compare=False)    # the project asked of
    public: bool = False    # asked for anyone under a public name (web: open: read)

    @property
    def end(self) -> float:
        return self.start + (self.points - 1) * self.step


@dataclass(frozen=True)
class Source:
    """What a source's module is asked through: its name, and for ``promql`` the VictoriaMetrics that holds the
    readings (``url``) and the label it holds every query to (``options["extra_label"]``: this project's)."""
    name: str
    type: str
    url: str = ""
    options: dict = field(default_factory=dict)


ASKING: ContextVar = ContextVar("asking", default=None)   # the project asking, while a source answers (sql.py reads
#                                                          the asking project's own items: ``ASKING.get()``)


def _module(name: str):
    if name == PROMQL:
        from . import promql
        return promql
    from . import sql
    return sql


def canonical(name: str) -> str:
    """The source's name: ``promql`` or ``sql``, an old name for one read as it (``OLD_NAMES``)."""
    return OLD_NAMES.get(name, name)


def language(name: str) -> str | None:
    """The language a source is asked in, or None for no source of that name."""
    name = canonical(name)
    return _module(name).LANGUAGE if name in NAMES else None


_ANSWERS: dict[str, tuple[float, bool]] = {}
_ANSWERS_LOCK = threading.Lock()


def _vm_answers(url: str) -> bool:
    """Whether VictoriaMetrics answers at ``url``: asked at most once every CHECKED_EVERY seconds."""
    from ..storage import answers
    now = time.monotonic()
    with _ANSWERS_LOCK:
        got = _ANSWERS.get(url)
    if got is not None and now - got[0] < CHECKED_EVERY:
        return got[1]
    ok = answers(url, wait=0.5)
    with _ANSWERS_LOCK:
        _ANSWERS[url] = (now, ok)
    return ok


def unavailable(name: str, store=None, project=None) -> str | None:
    """Why source ``name`` cannot be asked now, or None when it can. ``store``: the project's measurements (its
    VictoriaMetrics); ``project``: the project asked of (whose item index the SQL source reads)."""
    name = canonical(name)
    if name == PROMQL:
        if store is None or not getattr(store, "base", None):
            return "this project has no measurements store, so there is no VictoriaMetrics to ask"
        if not _vm_answers(store.base):
            from ..storage import not_answering
            return not_answering(store.base)
        return None
    if name == SQL:
        if project is None:
            return "the SQL source reads the asking project's items, and no project asked"
        from ..spec.itemindex import state_dir
        if state_dir(getattr(project, "events", None)) is None or not hasattr(project.events, "generation"):
            return "this project's record is kept nowhere on disk, so it has no item index to read"
        return None
    return f"ergostat has two data sources, {PROMQL} and {SQL}; {name!r} is neither"


def listed(store=None, project=None, reader: bool = False) -> list[dict]:
    """The two sources a panel can query, always both, in order: ``name``, ``type`` and ``language``, ``available``
    and, when it is not, ``reason``: why it cannot be asked now and what would make it so. ``reader``: anyone under
    a public name, who may ask neither (``READER``); the built-in shortcuts, which write their own queries, still
    answer them."""
    out = []
    for name in NAMES:
        why = READER if reader else unavailable(name, store, project)
        out.append({"name": name, "type": name, "language": _module(name).LANGUAGE, "available": why is None,
                    **({"reason": why} if why else {})})
    return out


def _source(name: str, store=None):
    """The source of this name, as its module is asked it, and the module; SourceError when there is none."""
    name = canonical(name)
    if name not in NAMES:
        raise SourceError("unknown", f"ergostat has two data sources, {PROMQL} and {SQL}; {name!r} is neither")
    if name == PROMQL:
        if store is None or not getattr(store, "base", None):
            raise SourceError("unreachable", "this project has no measurements store, so there is no VictoriaMetrics "
                                             "to ask")
        return Source(PROMQL, PROMQL, store.base, {"extra_label": f"project={store.project}"}), _module(name)
    return Source(SQL, SQL), _module(name)


def _text(mod, text, given) -> str:
    """The text as it is sent: not empty, the variables ``given`` written in by its language's rules, and bounded."""
    from ._interpolate import interpolate
    if not isinstance(text, str) or not text.strip():
        raise SourceError("refused", f"the query text is empty; write it in {mod.LANGUAGE}")
    for t in (text, sent := interpolate(mod.LANGUAGE, text, given or {})):
        if len(t) > MOST_TEXT:
            raise SourceError("limit", f"the query is {len(t)} characters, more than the {MOST_TEXT} allowed")
    return sent


def values(name: str, text: str, since: float, until: float, seconds: float = MOST_SECONDS,
           given: dict | None = None, store=None) -> list[str]:
    """A variable's values: ``label_values(label)`` or ``label_values(selector, label)`` asked of source ``name`` over
    [since, until], at most MOST_VALUES of them, each at most MOST_VALUE characters; SourceError otherwise. ``store``:
    the project's measurements (for ``promql``)."""
    src, mod = _source(name, store)
    m = _LABEL_VALUES.match(_text(mod, text, given))
    if not m:
        raise SourceError("refused", "a variable's query is label_values(label) or label_values(selector, label)")
    if not callable(getattr(mod, "values", None)):
        raise SourceError("refused", f"source {src.name!r} cannot list a label's values")
    if not 0 < until - since <= MOST_WINDOW:
        raise SourceError("limit", f"the window is more than the {int(MOST_WINDOW // 86400)} days allowed")
    if seconds <= 0:
        raise SourceError("limit", "busy: this request has no time left to ask; try again")
    w = Window(since, until, since, until - since, 1, min(seconds, MOST_SECONDS))
    got = mod.values(src, (m.group(1) or "").strip() or None, m.group(2), w)
    if not isinstance(got, list) or not all(isinstance(v, str) for v in got):
        raise SourceError("refused", f"source {src.name!r} answered with no list of values")
    if len(got) > MOST_VALUES:
        raise SourceError("limit", f"the label has {len(got)} values, more than the {MOST_VALUES} a variable may list; "
                                   "narrow the selector")
    if any(len(v) > MOST_VALUE for v in got):
        raise SourceError("limit", f"a value is longer than the {MOST_VALUE} characters a variable may hold")
    return sorted(set(got))


def query(spec, name: str, text: str, g, seconds: float = MOST_SECONDS, given: dict | None = None,
          store=None, project=None, public: bool = False) -> dict:
    """One panel query over the grid ``g`` (query/buckets.py): ``{times, step, series, unit}``, or SourceError.
    ``given``: the dashboard's variables it may use, name to the values selected (``_interpolate``); ``store``: the
    project's measurements (for ``promql``); ``project``: the project asked of, given to the source in its window and
    while it answers (``ASKING``); ``public``: asked for a public reader."""
    src, mod = _source(name, store)
    text = _text(mod, text, given)
    if g.until - g.since > MOST_WINDOW:
        raise SourceError("limit", f"the window is more than the {int(MOST_WINDOW // 86400)} days allowed")
    if g.n > MOST_POINTS + 1:                       # (aligned to its step, a window can touch one bucket more)
        raise SourceError("limit", f"the window has {g.n} points, more than the {MOST_POINTS} allowed")
    if seconds <= 0:
        raise SourceError("limit", "busy: this request has no time left to ask; try again")
    turned: list = []
    if src.name == PROMQL:                          # a saved query's old names, and the new
        from ..promnames import convert, names_for
        text, turned = convert(text, names_for(spec), both=True)
    w = Window(g.since, g.until, g.start, g.step, g.n, min(seconds, MOST_SECONDS), project, public)
    token = ASKING.set(project)
    try:
        got = mod.query(src, text, w)
    finally:
        ASKING.reset(token)
    warned = _lint.warnings(mod.LANGUAGE, text) + [("old-name", f"read under the model's own name: {x}") for x in turned]
    if isinstance(got, dict):                       # a typed frame (_frames.py)
        try:
            out = _frames.answer(got, g, MOST_SERIES)
            if out["shape"] == "graph":                 # fitted to a panel, with its matrix, as ergostat's own are
                from ..query.graphs import panel
                out = panel(out, {})
        except _frames.Bad as e:
            raise SourceError("limit" if isinstance(e, _frames.TooMany) else "refused",
                              f"source {src.name!r} answered badly: {e}" if e.code is None else f"source {src.name!r}: {e}",
                              code=e.code) from e
        return {**out, "warnings": [*out.get("warnings", ()), *warned]}
    if not isinstance(got, list):
        raise SourceError("refused", f"source {src.name!r} answered with no series")
    if len(got) > MOST_SERIES:
        raise SourceError("limit", f"the query answered {len(got)} series, more than the {MOST_SERIES} a panel may draw; "
                                   "aggregate it (sum by, topk)")
    series = []
    for label, points in got:
        values: list = [None] * g.n
        for t, v in points:
            if g.since - g.step < t <= g.until and isinstance(v, int | float) and math.isfinite(v):
                values[g.at(t + 1e-6 * g.step)] = float(v)    # (a time on a bucket's start, never just before it)
        series.append({"name": str(label), "values": values})
    return {"times": g.times, "step": g.step, "series": series, "unit": "", "capped": 0, "read_log": False, "shape": "series",
            "warnings": warned}


def suggest(name: str, what: str, prefix: str = "", metric: str = "", label: str = "",
            seconds: float = SUGGEST_SECONDS, store=None, project=None) -> dict:
    """The names an editor may complete: ``{suggestions, more}``, at most MOST_SUGGESTIONS, each starting with ``prefix``
    (``more``: there were others, not sent). ``metric`` narrows labels and values to one metric's; ``label`` is whose
    values. Bounded like a query, whatever the source: in time, in what is asked and in what is answered."""
    src, mod = _source(name, store)
    if not callable(getattr(mod, "suggest", None)):
        raise SourceError("refused", f"source {src.name!r} suggests nothing")
    if what not in SUGGESTED:
        raise SourceError("refused", f"what is suggested is one of {', '.join(SUGGESTED)}, not {what!r}")
    if any(v and not _NAME.fullmatch(v) for v in (metric, label)) or (what == "values") != bool(label):
        raise SourceError("refused", "values are suggested for one label, a name (letters, digits, _ and :)")
    if not isinstance(prefix, str) or len(prefix) > 200:
        raise SourceError("limit", "what is typed is more than the 200 characters a suggestion takes")
    if seconds <= 0:
        raise SourceError("limit", "busy: this request has no time left to ask; try again")
    token = ASKING.set(project)
    try:
        got, more = mod.suggest(src, what, prefix, metric, label, min(seconds, SUGGEST_SECONDS), MOST_SUGGESTIONS)
    finally:
        ASKING.reset(token)
    names = sorted({n for n in got if isinstance(n, str) and n.startswith(prefix)})
    return {"suggestions": names[:MOST_SUGGESTIONS], "more": bool(more) or len(names) > MOST_SUGGESTIONS}
