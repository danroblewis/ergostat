"""What the record exercises (SPEC §12e): a part the model declares that has not moved in the record, or has not
varied, is **not exercised** by it. Its rate cannot be identified from that record, nor the parameters it carries:
that is a statement about identifiability, not about the boundary (Sterman, *Business Dynamics*, ch. 21: a test of
structure the record never stressed says nothing either way). A flow that has not moved yet is not evidence that
it does not exist: points are lost rarely (an outage), a queue of the owner's messages is empty until the owner
writes, and a short record may never exercise them. So a quiet part is never proposed for removal; it is said, as a
finding on the part (``not-exercised``), with the span of record it covers and why (it never moved, or it held one
value, so there is no variation to identify a parameter from). The estimator and the judge do not vouch for what
it carries until the record exercises it, and the finding clears the moment the part moves.

Removal is for structure with no declared reason that the record shows to be redundant (``inferred``, ``twin`` in
``structural.py``), and always waits for the owner."""

from __future__ import annotations

import time

from ..durations import human
from ..spec.ir import Spec
from . import observe as ob

STILL = 0.001                        # a level whose range is under this share of its mean held one value
DEAD_MEAN, DEAD_PEAK = 0.001, 0.01   # a rate read under these shares of the typical flow's, on average and at its peak
MIN_READINGS = 20                    # fewer readings than this say nothing either way
MIN_SPAN = 600.0                     # nor does less record than this (s)
CODE = "not-exercised"
MARK = "proposed by ergostat"        # what ergostat writes in the description of a part it adds: an inferred part
SUGGEST = "a step test or a planned disturbance that moves it would exercise it"


def inferred(x) -> bool:
    """A part (or a parameter) ergostat added itself, its description saying so: structure with no declared reason
    beyond what ergostat inferred."""
    return MARK in (getattr(x, "description", "") or "").lower()


def declared_reason(x) -> bool:
    """A part the owner gave a reason for: a description, and not one ergostat wrote for a part it inferred."""
    d = (getattr(x, "description", "") or "").strip()
    return bool(d) and not inferred(x)


def _num(v: float) -> str:
    return f"{v:.3g}" if abs(v) < 1e4 else f"{v:.0f}"


def _clock(t: float) -> str:
    return time.strftime("%H:%M", time.localtime(t))


def quiet(spec: Spec, data: ob.Data | None, least: float = MIN_SPAN, readings: int = MIN_READINGS) -> dict[str, dict]:
    """Each stock, flow and auxiliary the record has readings of and does not exercise: ``ref`` → ``{why, says,
    since, until, span, readings}``; ``why`` is ``never-moved`` or ``no-variation``. A part with too few readings,
    or none, is not judged (nothing measures it, or the record is too short to say)."""
    if data is None:
        return {}
    g = data.grid
    edges = g.edges()
    lo_t, hi_t = _extent(data)
    inside = [i for i in range(g.n) if edges[i + 1] > lo_t and edges[i] < hi_t]   # the buckets the record reaches
    if not inside or min(hi_t, g.until) - max(lo_t, g.since) < least:
        return {}
    out: dict[str, dict] = {}

    def series_of(ref: str) -> list[tuple[int, float]]:
        vals = data.values.get(ref) or []
        return [(i, vals[i]) for i in inside if i < len(vals) and vals[i] is not None]
    rates = {}
    for n in spec.flows:
        ref = f"flow.{n}"
        if data.how.get(ref) in ("declared", "not measured"):
            continue
        rates[ref] = series_of(ref)
    means = [sum(abs(v) for _, v in r) / len(r) for r in rates.values() if r and any(v for _, v in r)]
    typical = sum(means) / len(means) if means else 0.0

    def say(ref: str, why: str, words: str, got: list[tuple[int, float]]) -> None:
        a, b = max(edges[got[0][0]], lo_t, g.since), min(edges[got[-1][0] + 1], hi_t, g.until)
        out[ref] = {"ref": ref, "why": why, "says": words, "since": a, "until": b, "span": b - a, "readings": len(got)}
    for ref, got in rates.items():
        if len(got) < readings:
            continue
        r = [abs(v) for _, v in got]
        counted = ob.is_counted(data, ref)
        peak, mean = max(r), sum(r) / len(r)
        if peak == 0 or (typical > 0 and mean < DEAD_MEAN * typical and peak < DEAD_PEAK * typical):
            say(ref, "never-moved", f"it never moved (at most {_num(peak)} an hour"
                + (f", where flows here move {_num(typical)}" if typical > 0 else "") + ")", got)
            continue
        vals = [v for _, v in got]
        if not counted and max(vals) - min(vals) <= STILL * max(abs(mean), 1e-9):
            say(ref, "no-variation", f"it ran at a steady {_num(mean)} an hour: no variation to identify a parameter from",
                got)
    for kind, table in (("stock", spec.stocks), ("auxiliary", spec.auxiliaries)):
        for n in table:
            ref = f"{kind}.{n}"
            got = series_of(ref)
            if len(got) < readings:
                continue
            lv = [v for _, v in got]
            lo, hi = min(lv), max(lv)
            m = sum(abs(v) for v in lv) / len(lv)
            if hi - lo > max(1e-9, STILL * m):
                continue
            if m <= 1e-9:
                say(ref, "never-moved", "it never moved (0 the whole time)", got)
            else:
                say(ref, "no-variation", f"it held at {_num(lo)} the whole time: no variation to identify a parameter from",
                    got)
    return out


def _extent(data: ob.Data) -> tuple[float, float]:
    """The span the record reaches: from the first reading of any level or flow read to the last (a counted flow
    counts nothing where the record has not reached, which is not a flow that did not move)."""
    g = data.grid
    edges = g.edges()
    lo, hi = None, None
    for ts in data.at.values():
        for t in ts:
            if t is not None:
                lo, hi = (t if lo is None else min(lo, t)), (t if hi is None else max(hi, t))
    for ref, vals in data.values.items():
        if ref in data.at or ob.is_counted(data, ref) or data.how.get(ref) in ("declared", "not measured"):
            continue
        idx = [i for i, v in enumerate(vals) if v is not None]
        if idx:
            lo = edges[idx[0]] if lo is None else min(lo, edges[idx[0]])
            hi = edges[idx[-1] + 1] if hi is None else max(hi, edges[idx[-1] + 1])
    for c in data.counted.values():
        if c.times:
            lo = c.times[0] if lo is None else min(lo, c.times[0])
            hi = c.times[-1] if hi is None else max(hi, c.times[-1])
    if lo is None:
        return g.since, g.until
    return max(g.since, lo), min(g.until, hi + g.width)


def users(spec: Spec, parameter: str) -> list[str]:
    return [f"{k}.{x.name}" for k, t in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)) for x in t.values()
            if x.equation and parameter in x.equation.parameters]


def parameter_quiet(spec: Spec, data: ob.Data | None, parameter: str, q: dict[str, dict] | None = None) -> dict | None:
    """Why a parameter cannot be identified from the record, or None: every part it acts through that the record
    reads is not exercised (a parameter of parts nothing reads is not judged here)."""
    q = quiet(spec, data) if q is None else q
    via = users(spec, parameter)
    read = [r for r in via if any(v is not None for v in (data.values.get(r) if data else None) or [])
            and (data.how.get(r) not in ("declared", "not measured"))]
    if not read or any(r not in q for r in read):
        return None
    first = q[read[0]]
    return {**first, "ref": f"parameter.{parameter}", "via": read,
            "says": f"it acts only through {', '.join(read)}, which the record has not exercised ({first['says']})"}


def said(x: dict) -> str:
    """The finding's words: what, why, over which span of record, and that it is not evidence of absence."""
    kind, _, name = x["ref"].partition(".")
    return (f"{kind} {name}: not exercised by the record: {x['says']} over {human(x['span'])} of record "
            f"({_clock(x['since'])} to {_clock(x['until'])}, {x['readings']} readings). Its rate cannot be identified from "
            f"this record, which is not evidence it is absent: it is kept, and nothing is estimated or judged from it "
            f"until the record moves it ({SUGGEST})")


def findings(spec: Spec, data: ob.Data | None) -> list[tuple[str, str]]:
    """``(about, message)`` for every part the record does not exercise."""
    return [(ref, said(x)) for ref, x in sorted(quiet(spec, data).items())]


_CACHE: dict = {}


def of_project(p, spec: Spec, now: float | None = None) -> tuple[ob.Data, dict[str, dict]]:
    """The record on the reference window (the last day, as the estimates read it) and what it does not exercise;
    kept a minute for the same model."""
    from . import version as ver
    at = now if now is not None else time.time()
    key = (str(p.dir), ver.version(spec), int(at // 60))
    got = _CACHE.get(key[0])
    if got and got[0] == key:
        return got[1]
    data = ob.measured(p, ob.reference(p, at), spec)
    out = (data, quiet(spec, data))
    _CACHE[key[0]] = (key, out)
    return out
