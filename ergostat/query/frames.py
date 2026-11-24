"""Each answer's shape (SPEC §4e, *Result shapes*): one of five typed frames, so a chart is chosen by what the data is,
not by where it came from, and a PromQL and a SQL answer of one shape draw the same chart.

- ``series``: values over one time axis. ``roles`` says what they are when it matters: ``input`` and ``output`` (two
  signals, drawn one against the other) or ``open``, ``high``, ``low`` and ``close`` (candles).
- ``table``: dimensions to measures, as ``dims``, ``measures`` and ``rows`` (each row its dims' values, then its measures').
- ``points``: one row per observation, X and Y both numbers; ``order: "time"`` when the order is the content.
- ``distribution``: how values spread; ``form`` is ``bins``, ``samples`` or ``quartiles``.
- ``response``: how a system responds; ``has`` holds ``frequency`` and, from a model, ``system`` (its poles and zeros).

Every answer also carries the envelope ``meta``: its source, its query text (a data source's), its provenance and its
verdict (``ok``, ``warn`` or ``refuse``, with the reasons). The catalog's sixth shape, ``graph``, is not here yet."""

from __future__ import annotations

SHAPES = ("series", "table", "points", "distribution", "response")
TWO_SIGNALS = ["input", "output"]
CANDLE = ["open", "high", "low", "close"]
FRAME_KEYS = ("shape", "roles", "order", "form", "has", "dims", "measures", "rows")


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
        return {"level": "refuse", "reasons": [{"code": got.get("error_kind") or "unanswerable", "says": got["error"]}]}
    if got.get("supported") is False:
        return {"level": "refuse", "reasons": [{"code": "no-coherence", "says": got.get("refused") or ""}]}
    said = [w for w in (got.get("note"), "only part of the record was read" if got.get("truncated") else None) if w]
    return {"level": "warn", "reasons": [{"code": "partial", "says": w} for w in said]} if said else {"level": "ok", "reasons": []}


def framed(got: dict, q) -> dict:
    """The answer to ``q`` with its frame and envelope, as a new dict (a kept answer is shared, and never changed)."""
    method = got.get("method")
    meta = {"source": getattr(q, "source", None), "query": getattr(q, "text", None),
            "provenance": got.get("provenance") or ("declared" if method == "model" else "derived" if method == "empirical"
                                                    else "observed"),
            "verdict": _verdict(got)}
    if got.get("error"):
        return {**got, "meta": meta}
    return {**got, **describe(got, getattr(q, "agg", None)), "meta": meta}
