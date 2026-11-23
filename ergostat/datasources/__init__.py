"""Dashboard data sources (SPEC §4e, *Data sources*; §11): a named connection under the model's ``sources:``, a query language, and a
read-only ``query`` that answers a time window as series. A panel query is ``{"source": name, "text": ...}``, the text in
the source's own language; the answer has the shape of every chart's (``times``, ``step``, ``series``).

A type is one module in this package, found by its name: ``TYPE`` (the word in ``sources:``), ``KEYS`` (its connection
keys besides ``type``), ``LANGUAGE`` (what its text is written in) and ``query(source, text, window)``, which returns
``[(name, [(time, value), ...]), ...]``. It may also offer ``suggest(source, what, prefix, metric, label, seconds,
most)``, the names an editor completes (``what``: ``metrics``, ``labels`` or ``values``), read from the source's own
metadata. It offers nothing else: a module with any other public function or class is refused, so ``query`` and
``suggest`` are the only operations anything can call on a source (and each must itself only read).
Every query is bounded here, whatever its type: its text, its window, its points and its series, and it is refused
with words naming the bound it is over."""

from __future__ import annotations

import importlib
import math
import pkgutil
import re
import threading
from dataclasses import dataclass
from types import FunctionType, ModuleType

MOST_TEXT = 4000            # characters of a query's text
MOST_SERIES = 50            # series one query may answer with
MOST_POINTS = 1000          # buckets in a window
MOST_WINDOW = 400 * 86400.0
MOST_SECONDS = 10.0         # the longest one query may take to answer
OFFERED = {"TYPE", "KEYS", "LANGUAGE", "query", "suggest"}
MOST_SUGGESTIONS = 100      # names one suggestion answers with
SUGGEST_SECONDS = 3.0
SUGGESTED = ("metrics", "labels", "values")
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

    @property
    def end(self) -> float:
        return self.start + (self.points - 1) * self.step


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
        raise TypeError(f"data source type {mod.TYPE}: offers {extra[0]}; a type offers only query and suggest (read-only)")
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


def listed(spec) -> list[dict]:
    """The model's sources a panel can query: name, type and language, and never their connection."""
    every = types()
    return [{"name": s.name, "type": s.type, "language": every[s.type].LANGUAGE}
            for s in (getattr(spec, "sources", None) or {}).values() if s.type in every]


def query(spec, name: str, text: str, g, seconds: float = MOST_SECONDS) -> dict:
    """One panel query over the grid ``g`` (query/buckets.py): ``{times, step, series, unit}``, or SourceError."""
    src = (getattr(spec, "sources", None) or {}).get(name)
    if src is None:
        raise SourceError("unknown", f"no source named {name!r} under sources:")
    mod = types().get(src.type)
    if mod is None:
        raise SourceError("unknown", f"source {name!r} is of type {src.type}, which panels cannot query")
    if not isinstance(text, str) or not text.strip():
        raise SourceError("refused", f"the query text is empty; write it in {mod.LANGUAGE}")
    if len(text) > MOST_TEXT:
        raise SourceError("limit", f"the query is {len(text)} characters, more than the {MOST_TEXT} allowed")
    if g.until - g.since > MOST_WINDOW:
        raise SourceError("limit", f"the window is more than the {int(MOST_WINDOW // 86400)} days allowed")
    if g.n > MOST_POINTS + 1:                       # (aligned to its step, a window can touch one bucket more)
        raise SourceError("limit", f"the window has {g.n} points, more than the {MOST_POINTS} allowed")
    if seconds <= 0:
        raise SourceError("limit", "busy: this request has no time left to ask; try again")
    w = Window(g.since, g.until, g.start, g.step, g.n, min(seconds, MOST_SECONDS))
    got = mod.query(src, text, w)
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
    return {"times": g.times, "step": g.step, "series": series, "unit": "", "capped": 0, "read_log": False}


def suggest(spec, name: str, what: str, prefix: str = "", metric: str = "", label: str = "",
            seconds: float = SUGGEST_SECONDS) -> dict:
    """The names an editor may complete: ``{suggestions, more}``, at most MOST_SUGGESTIONS, each starting with ``prefix``
    (``more``: there were others, not sent). ``metric`` narrows labels and values to one metric's; ``label`` is whose
    values. Bounded like a query, whatever the type: in time, in what is asked and in what is answered."""
    src = (getattr(spec, "sources", None) or {}).get(name)
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
    got, more = mod.suggest(src, what, prefix, metric, label, min(seconds, SUGGEST_SECONDS), MOST_SUGGESTIONS)
    names = sorted({n for n in got if isinstance(n, str) and n.startswith(prefix)})
    return {"suggestions": names[:MOST_SUGGESTIONS], "more": bool(more) or len(names) > MOST_SUGGESTIONS}
