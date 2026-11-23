"""Dashboard data sources (SPEC §4e, *Data sources*; §11): a named connection under the model's ``sources:``, a query language, and a
read-only ``query`` that answers a time window as series. A panel query is ``{"source": name, "text": ...}``, the text in
the source's own language; the answer has the shape of every chart's (``times``, ``step``, ``series``).

A type is one module in this package, found by its name: ``TYPE`` (the word in ``sources:``), ``KEYS`` (its connection
keys besides ``type``), ``LANGUAGE`` (what its text is written in) and ``query(source, text, window)``, which returns
``[(name, [(time, value), ...]), ...]``, or a typed frame (series with roles, a table or points: _frames.py). It offers
nothing else: a module with any other public function or class is refused, so ``query`` is the one operation anything
can call on a source (and a type's ``query`` must itself only read).
Every query is bounded here, whatever its type: its text, its window, its points and its series, and it is refused
with words naming the bound it is over."""

from __future__ import annotations

import importlib
import math
import pkgutil
import threading
from dataclasses import dataclass
from types import FunctionType, ModuleType

from . import _frames

MOST_TEXT = 4000            # characters of a query's text
MOST_SERIES = 50            # series one query may answer with
MOST_POINTS = 1000          # buckets in a window
MOST_WINDOW = 400 * 86400.0
MOST_SECONDS = 10.0         # the longest one query may take to answer
OFFERED = {"TYPE", "KEYS", "LANGUAGE", "query"}


class SourceError(Exception):
    """A query that is not answered, and why: ``kind`` is ``limit``, ``unreachable``, ``refused`` or ``unknown``."""

    def __init__(self, kind: str, words: str):
        super().__init__(words)
        self.kind = kind


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
        raise TypeError(f"data source type {mod.TYPE}: offers {extra[0]}; a type offers only query (read-only)")
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
