"""Each answer's shape (SPEC §4e, *Result shapes*): one of six typed frames, so a chart is chosen by what the data is,
not by where it came from, and a PromQL and a SQL answer of one shape draw the same chart.

- ``series``: values over one time axis. ``roles`` says what they are when it matters: ``input`` and ``output`` (two
  signals, drawn one against the other) or ``open``, ``high``, ``low`` and ``close`` (candles).
- ``table``: dimensions to measures, as ``dims``, ``measures`` and ``rows`` (each row its dims' values, then its measures').
- ``points``: one row per observation, X and Y both numbers; ``order: "time"`` when the order is the content.
- ``distribution``: how values spread; ``form`` is ``bins``, ``samples`` or ``quartiles``.
- ``response``: how a system responds; ``has`` holds ``frequency`` and, from a model, ``system`` (its poles and zeros).

- ``graph``: nodes and edges of one named ``kind`` of diagram (only a data source's frame, checked in _frames.py).

Every answer also carries the envelope ``meta``: its source, its query text (a data source's), its provenance, its
verdict (verdicts.py: ``ok``, ``warn`` or ``refuse``, each reason with its fix), ``n`` (the values it holds) and
``sampling`` (its step). ``n_effective`` and the sampling's scrape, range windows and observable band are ``None``:
not known here (analysis-source-and-window-guard measures them), and never a guess. A refused answer holds nothing to
draw."""

from __future__ import annotations

from .verdicts import reason, verdict

SHAPES = ("series", "table", "points", "distribution", "response", "graph")
TWO_SIGNALS = ["input", "output"]
CANDLE = ["open", "high", "low", "close"]
FRAME_KEYS = ("shape", "roles", "order", "form", "has", "dims", "measures", "rows", "kind")


def _rows(series: list[dict]) -> list[list]:
    xs = (series[0].get("xs") or []) if series else []
    return [[x, *(s["values"][i] if i < len(s.get("values") or []) else None for s in series)] for i, x in enumerate(xs)]


def describe(got: dict, agg: str | None = None) -> dict:
    """An answer's frame, read from how the engine built it. ``agg``: the query's; a count in bins is a distribution."""
    if got.get("shape") in SHAPES:                     # a data source's, typed already
        return {k: got[k] for k in FRAME_KEYS if k in got}
    if "frequency" in got:
        return {"shape": "response", "has": ["frequency", "system"] if got.get("poles") is not None else ["frequency"]}
    x, series = got.get("x"), got.get("series") or []
    if x is None:
        return {"shape": "series", "roles": CANDLE} if any("close" in s for s in series) else {"shape": "series"}
    ty = x.get("type")
    if ty == "query":
        return {"shape": "series", "roles": TWO_SIGNALS}
    if ty == "field":
        return {"shape": "points"}
    if ty == "category" and x.get("distribution"):
        return {"shape": "distribution", "form": "samples"}
    if ty == "bins" and agg == "count":
        return {"shape": "distribution", "form": "bins"}
    dim = {"name": x.get("label") or "", "type": "string" if ty == "category" else "number"}
    if x.get("edges") is not None:
        dim["edges"] = x["edges"]
    return {"shape": "table", "dims": [dim], "measures": [{"name": s["name"], "unit": got.get("unit") or ""} for s in series],
            "rows": _rows(series)}


def _verdict(got: dict) -> dict:
    if got.get("error"):
        busy = "busy:" in got["error"]                  # (a request out of time, whatever asked: try again)
        return verdict([reason(got.get("error_code") or ("busy" if busy else got.get("error_kind") or "unanswerable"), got["error"])])
    if got.get("supported") is False:                  # (no curve is sent with it: query/frequency.py)
        return verdict([reason("no-coherence", got.get("refused") or "")])
    said = [w for w in (got.get("note"), "only part of the record was read" if got.get("truncated") else None) if w]
    return verdict([reason("partial", w) for w in said] + [reason(c, w) for c, w in got.get("warnings") or ()])


def _n(got: dict) -> int:
    """How many values an answer holds: its series' or points' values, a table's cells, a graph's nodes, a response's
    frequencies."""
    if got.get("shape") == "graph":
        return len(got["nodes"]["id"])
    if "frequency" in got:
        return len((got.get("frequency") or {}).get("hz") or [])
    return sum(v is not None for s in got.get("series") or [] for v in s.get("close") or s.get("values") or [])


def framed(got: dict, q) -> dict:
    """The answer to ``q`` with its frame and envelope, as a new dict (a kept answer is shared, and never changed).
    A refused answer keeps nothing to draw: its id, its error and the envelope."""
    method = got.get("method")
    meta = {"source": getattr(q, "source", None), "query": getattr(q, "text", None),
            "provenance": "declared" if method == "model" else "derived" if method == "empirical" else "observed",
            "verdict": _verdict(got)}
    if got.get("error"):
        return {**{k: got[k] for k in ("id", "error", "error_kind", "error_at", "read_log") if k in got}, "meta": meta}
    meta.update(n=_n(got), n_effective=None, sampling={"step_s": got.get("step"), "scrape_s": None,
                                                       "range_windows_s": None, "observable_period_s": None})
    return {**{k: v for k, v in got.items() if k != "warnings"}, **describe(got, getattr(q, "agg", None)), "meta": meta}
