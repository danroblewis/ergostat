"""The window ledger (SPEC §4e, *Sampling*): what each answer was sampled at, and so which periods it can show.

- ``scrape_s``: the readings' own spacing where they are read; null where it is not known, and then the verdict warns
  (``scrape-unknown``) and the band's low end comes from the step alone: an unknown scrape never counts as fine.
- ``range_windows_s``: every ``[d]`` and ``[d:r]`` of a PromQL text (its ``d``), or a moving average's span.
- ``observable_period_s``: ``[2 × max(scrape, step), window / 2]`` (G2: a period under two samples is aliased; one
  over half the window is not seen twice).
- ``nulls_s``: each period ``W/k`` of a range window ``W`` inside that band, where an average over ``W`` shows nothing
  (G1); at most ``MOST_NULLS``, the longest first.

A request whose answers differ in step or range windows warns on each, naming them all (G4)."""

from __future__ import annotations

import math
import re

from .verdicts import reason, verdict

MOST_NULLS = 50
_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0, "w": 604800.0, "y": 31536000.0}
_QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`[^`]*`|#[^\n]*')
_RANGE = re.compile(r"\[\s*((?:\d+(?:\.\d+)?(?:ms|[smhdwy]))+)\s*(?::[^\]]*)?\]")
_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|[smhdwy])")


SCRAPE_READINGS = 2_000                # the newest readings an answer's scrape interval is read from


def spacing(times: list[float]) -> float | None:
    """The median spacing of readings at ``times`` (in order; the lower of two middles), apart from readings at one
    time, or None."""
    d = sorted(b - a for a, b in zip(times, times[1:], strict=False) if b > a)
    return d[(len(d) - 1) // 2] if d else None


def scrape(m, series: str, since: float, until: float) -> float | None:
    """A series' scrape interval in a window (of its newest ``SCRAPE_READINGS``: every answer of a series pays it);
    None where it is not known."""
    return spacing([t for t, _ in m.range(series, since, until, last=SCRAPE_READINGS)])


def scrapes(m, qs, since: float, until: float) -> dict:
    """``{"scrape_s": ...}`` of an answer built from the readings of the ``series`` queries among ``qs``: the coarsest
    of their scrapes, None if any is unknown; ``{}`` where none is a series (not sampled)."""
    got = [scrape(m, q.series, since, until) for q in qs if getattr(q, "source", None) == "series"]
    return {"scrape_s": None if None in got else max(got)} if got else {}


def windows(text: str) -> list[float]:
    """The range windows of a PromQL text, in seconds, each once (strings and comments are not read)."""
    plain = _QUOTED.sub('""', text)
    return sorted({sum(float(n) * _UNITS[u] for n, u in _PART.findall(m[1])) for m in _RANGE.finditer(plain)})


def _d(s: float) -> str:
    return f"{s:g} s"


def ledger(got: dict, q, window: float | None) -> tuple[dict, list[tuple[str, str]]]:
    """``meta.sampling`` of one answer, and what it warns. ``scrape_s`` in ``got``: its values are readings, sampled."""
    step, scrape = got.get("step"), got.get("scrape_s")
    ws = got["range_windows_s"] if "range_windows_s" in got else \
        [q.window * step] if getattr(q, "transform", None) == "moving_avg" and step else []
    said = []
    if "scrape_s" in got and scrape is None:
        said.append(("scrape-unknown", "the readings' scrape interval is not known, so the shortest period this can show "
                                       "is taken from the step alone, and may be longer"))
    finest = max((x for x in (scrape, step) if x), default=None)
    lo, hi = (2 * finest if finest else None), (window / 2 if window else None)
    nulls: list[float] = []
    for w in (ws or ()) if lo else ():                 # (None: a language whose windows are not read)
        first = max(1, math.ceil(w / hi - 1e-9)) if hi else 1
        for k in range(first, first + MOST_NULLS):     # each window's longest, then all windows' longest
            if w / k < lo:
                break
            nulls.append(w / k)
    return ({"step_s": step, "scrape_s": scrape, "range_windows_s": ws, "observable_period_s": [lo, hi],
             "nulls_s": sorted(set(nulls), reverse=True)[:MOST_NULLS]}, said)


def mixed(results: list[dict]) -> None:
    """Each answer of a request whose answers differ in step or range windows warns, naming every one (in place)."""
    live = [r["meta"] for r in results if "error" not in r]
    steps = sorted({m["sampling"]["step_s"] for m in live if m["sampling"]["step_s"]})
    wins = {tuple(m["sampling"]["range_windows_s"] or ()) for m in live}
    if len(steps) < 2 and len(wins) < 2:
        return
    every = sorted({w for ws in wins for w in ws})
    says = (f"this request's answers differ: steps {', '.join(map(_d, steps)) or 'none'}; range windows "
            f"{', '.join(map(_d, every)) or 'none'}, so they cannot be compared period for period")
    for m in live:
        m["verdict"] = verdict([*m["verdict"]["reasons"], reason("mixed-windows", says)])
