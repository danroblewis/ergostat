"""Dashboard data sources (SPEC §4e, *Data sources*; §11): a named connection under the model's ``sources:``, a query language, and a
read-only ``query`` that answers a time window as series. A panel query is ``{"source": name, "text": ...}``, the text in
the source's own language; the answer has the shape of every chart's (``times``, ``step``, ``series``).

A type is one module in this package, found by its name: ``TYPE`` (the word in ``sources:``), ``KEYS`` (its connection
keys besides ``type``), ``LANGUAGE`` (what its text is written in) and ``query(source, text, window)``, which returns
``[(name, [(time, value), ...]), ...]``, or a typed frame (series with roles, a table or points: _frames.py). It may
also offer ``suggest(source, what, prefix, metric, label, seconds, most)``, the names an editor completes (``what``:
``metrics``, ``labels`` or ``values``), read from the source's own metadata, and ``values(source, selector, label,
window)``, the values a label takes, which a dashboard variable written ``label_values(selector, label)`` lists
(``values`` here). It offers nothing else: a module with any other public function or class is refused, so ``query``,
``suggest`` and ``values`` are the only operations anything can call on a source (and each must itself only read).
Every query is bounded here, whatever its type: its text, its window, its points and its series, and it is refused
with words naming the bound it is over."""

from __future__ import annotations

import importlib
import math
import pkgutil
import re
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from types import FunctionType, ModuleType

from . import _frames

MOST_TEXT = 4000            # characters of a query's text
MOST_SERIES = 50            # series one query may answer with
MOST_POINTS = 1000          # buckets in a window
MOST_WINDOW = 400 * 86400.0
MOST_SECONDS = 10.0         # the longest one query may take to answer
MOST_VALUES = 200           # values a variable's query may list
MOST_VALUE = 200            # characters of one value
OFFERED = {"TYPE", "KEYS", "LANGUAGE", "query", "suggest", "values"}
_LABEL_VALUES = re.compile(r"\s*label_values\(\s*(?:(.+)\s*,\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\Z", re.S)
MOST_SUGGESTIONS = 100      # names one suggestion answers with
SUGGEST_SECONDS = 3.0
SUGGESTED = ("metrics", "labels", "values")
OWN_NAME = OWN_TYPE = "model"   # the source that is the project's own model (datasources/model.py)
_NAME = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]{0,199}")     # a metric's or a label's name, as a suggestion takes it


class SourceError(Exception):
    """A query that is not answered, and why: ``kind`` is ``limit``, ``unreachable``, ``refused`` or ``unknown``."""

    def __init__(self, kind: str, words: str, at: tuple[int, int] | None = None):
        super().__init__(words)
        self.kind = kind
        self.at = at            # (line, column), each from 1: where in the text the source said it is wrong


@dataclass(frozen=True)
class Window:
    """What a type is asked for: ``points`` values, one at each of ``start + i * step``, within [since, until]."""
    since: float
    until: float
    start: float
    step: float
    points: int
    seconds: float          # how long it may take
    project: object = field(default=None, compare=False)    # the project asked of (a model source reads its own)
    public: bool = False    # asked for anyone under a public name (web: open: read)

    @property
    def end(self) -> float:
        return self.start + (self.points - 1) * self.step


ASKING: ContextVar = ContextVar("asking", default=None)   # the project asking, while a type answers (one reading the
#                                                          project's own record, sql.py, takes it: ``ASKING.get()``)
_TYPES: dict[str, ModuleType] = {}
_LOCK = threading.RLock()
_FOUND = False


def register(mod) -> None:
    """A type, checked: it says its type, keys and language, and offers ``query`` and nothing else."""
    names = {n for n in vars(mod) if not n.startswith("_") and n.isidentifier()}
    if not {"TYPE", "KEYS", "LANGUAGE", "query"} <= names or not callable(mod.query):
        raise TypeError(f"a data source type needs TYPE, KEYS, LANGUAGE and query: {getattr(mod, '__name__', mod)}")
    own = lambda v: isinstance(v, FunctionType | type) and (    # noqa: E731
        not isinstance(mod, ModuleType) or getattr(v, "__module__", None) == mod.__name__)
    extra = sorted(n for n in names - OFFERED if own(getattr(mod, n)))
    if extra:
        raise TypeError(f"data source type {mod.TYPE}: offers {extra[0]}; "
                        "a type offers only query, suggest and values (read-only)")
    with _LOCK:
        _TYPES[mod.TYPE] = mod


def unregister(name: str) -> None:
    with _LOCK:
        _TYPES.pop(name, None)


def types() -> dict[str, ModuleType]:
    """Every type there is: the modules of this package, and any registered."""
    global _FOUND
    with _LOCK:
        if not _FOUND:
            for m in pkgutil.iter_modules(__path__):
                if not m.name.startswith("_"):
                    register(importlib.import_module(f"{__name__}.{m.name}"))
            _FOUND = True
        return dict(_TYPES)


def _sources(spec) -> dict:
    """The model's sources, and the model itself as one named ``model`` unless a source declared takes that name: its
    connection is the project's own model and record (datasources/model.py), so it needs no declaring."""
    declared = getattr(spec, "sources", None) or {}
    if spec is None or OWN_NAME in declared:
        return declared
    from ..spec.ir import Source
    return {**declared, OWN_NAME: Source(OWN_NAME, OWN_TYPE)}


def listed(spec, own_only: bool = False) -> list[dict]:
    """The model's sources a panel can query: name, type and language, and never their connection. ``own_only``: only
    those that read nothing outside the project (what anyone under a public name may ask)."""
    every = types()
    return [{"name": s.name, "type": s.type, "language": every[s.type].LANGUAGE}
            for s in _sources(spec).values() if s.type in every and (not own_only or s.type == OWN_TYPE)]


def own(spec, name: str) -> bool:
    """Whether source ``name`` reads only the project's own model and record; an unknown name does not."""
    src = _sources(spec).get(name)
    return src is not None and src.type == OWN_TYPE


def _source(spec, name: str):
    src = _sources(spec).get(name)
    if src is None:
        raise SourceError("unknown", f"no source named {name!r} under sources:")
    mod = types().get(src.type)
    if mod is None:
        raise SourceError("unknown", f"source {name!r} is of type {src.type}, which panels cannot query")
    return src, mod


def _text(mod, text, given) -> str:
    """The text as it is sent: not empty, the variables ``given`` written in by its language's rules, and bounded."""
    from ._interpolate import interpolate
    if not isinstance(text, str) or not text.strip():
        raise SourceError("refused", f"the query text is empty; write it in {mod.LANGUAGE}")
    for t in (text, sent := interpolate(mod.LANGUAGE, text, given or {})):
        if len(t) > MOST_TEXT:
            raise SourceError("limit", f"the query is {len(t)} characters, more than the {MOST_TEXT} allowed")
    return sent


def values(spec, name: str, text: str, since: float, until: float, seconds: float = MOST_SECONDS,
           given: dict | None = None) -> list[str]:
    """A variable's values: ``label_values(label)`` or ``label_values(selector, label)`` asked of source ``name`` over
    [since, until], at most MOST_VALUES of them, each at most MOST_VALUE characters; SourceError otherwise."""
    src, mod = _source(spec, name)
    m = _LABEL_VALUES.match(_text(mod, text, given))
    if not m:
        raise SourceError("refused", "a variable's query is label_values(label) or label_values(selector, label)")
    if not callable(getattr(mod, "values", None)):
        raise SourceError("refused", f"source {name!r} ({src.type}) cannot list a label's values")
    if not 0 < until - since <= MOST_WINDOW:
        raise SourceError("limit", f"the window is more than the {int(MOST_WINDOW // 86400)} days allowed")
    if seconds <= 0:
        raise SourceError("limit", "busy: this request has no time left to ask; try again")
    w = Window(since, until, since, until - since, 1, min(seconds, MOST_SECONDS))
    got = mod.values(src, (m.group(1) or "").strip() or None, m.group(2), w)
    if not isinstance(got, list) or not all(isinstance(v, str) for v in got):
        raise SourceError("refused", f"source {name!r} answered with no list of values")
    if len(got) > MOST_VALUES:
        raise SourceError("limit", f"the label has {len(got)} values, more than the {MOST_VALUES} a variable may list; "
                                   "narrow the selector")
    if any(len(v) > MOST_VALUE for v in got):
        raise SourceError("limit", f"a value is longer than the {MOST_VALUE} characters a variable may hold")
    return sorted(set(got))


def query(spec, name: str, text: str, g, seconds: float = MOST_SECONDS, given: dict | None = None,
          project=None, public: bool = False) -> dict:
    """One panel query over the grid ``g`` (query/buckets.py): ``{times, step, series, unit}``, or SourceError.
    ``given``: the dashboard's variables it may use, name to the values selected (``_interpolate``); ``project``: the
    project asked of, given to the type in its window and while it answers (``ASKING``); ``public``: asked for a
    public reader."""
    src, mod = _source(spec, name)
    text = _text(mod, text, given)
    if g.until - g.since > MOST_WINDOW:
        raise SourceError("limit", f"the window is more than the {int(MOST_WINDOW // 86400)} days allowed")
    if g.n > MOST_POINTS + 1:                       # (aligned to its step, a window can touch one bucket more)
        raise SourceError("limit", f"the window has {g.n} points, more than the {MOST_POINTS} allowed")
    if seconds <= 0:
        raise SourceError("limit", "busy: this request has no time left to ask; try again")
    w = Window(g.since, g.until, g.start, g.step, g.n, min(seconds, MOST_SECONDS), project, public)
    token = ASKING.set(project)
    try:
        got = mod.query(src, text, w)
    finally:
        ASKING.reset(token)
    if isinstance(got, dict):                       # a typed frame (_frames.py)
        try:
            return _frames.answer(got, g, MOST_SERIES)
        except _frames.Bad as e:
            raise SourceError("limit" if isinstance(e, _frames.TooMany) else "refused", f"source {name!r} answered badly: {e}") from e
    if not isinstance(got, list):
        raise SourceError("refused", f"source {name!r} answered with no series")
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
    return {"times": g.times, "step": g.step, "series": series, "unit": "", "capped": 0, "read_log": False, "shape": "series"}


def suggest(spec, name: str, what: str, prefix: str = "", metric: str = "", label: str = "",
            seconds: float = SUGGEST_SECONDS, project=None) -> dict:
    """The names an editor may complete: ``{suggestions, more}``, at most MOST_SUGGESTIONS, each starting with ``prefix``
    (``more``: there were others, not sent). ``metric`` narrows labels and values to one metric's; ``label`` is whose
    values. Bounded like a query, whatever the type: in time, in what is asked and in what is answered."""
    src = _sources(spec).get(name)
    mod = types().get(src.type) if src is not None else None
    if mod is None:
        raise SourceError("unknown", f"no source named {name!r} under sources: that panels can query")
    if not callable(getattr(mod, "suggest", None)):
        raise SourceError("refused", f"source {name!r} ({src.type}) suggests nothing")
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
