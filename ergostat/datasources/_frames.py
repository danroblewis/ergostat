"""A data source's typed answer (SPEC §4e, *Result shapes*), made into what a panel draws. A type's ``query`` may answer
with a frame instead of a list of series:

- ``{"shape": "series", "time": [...], "series": [{"key", "unit"?, "role"?, "values": [...]}]}``: values at those times,
  placed on the panel's grid as a list of series is. Roles ``input`` and ``output`` make two signals, drawn one against
  the other; ``open``, ``high``, ``low`` and ``close`` make one series of candles.
- ``{"shape": "table", "dims": [{"name", "type"}], "measures": [{"name", "unit"?}], "rows": [[...], ...]}``: a dim is
  a ``string``, ``number`` or ``time``; a row holds its dims' values, then its measures' numbers.
- ``{"shape": "points", "x": {"name", "unit"?, "values"}, "y": {...}, "t"?: [...], "order"?: "time", "group"?: [...]}``.
- ``{"shape": "response", "frequency": {"hz", "re", "im", "magnitude_db", "phase_deg", "coherence"?}, "system"?: {"form",
  "gain", "tau", "delay", "poles": [[re, im]], "zeros": [...], "dt"?}, "path"?, "fit"?, "provenance"?}``: how a system
  responds; a model's carries ``system``, and its poles are the sampled model's at ``dt`` when it has one.

Whatever the type, a frame is checked and bounded here; one that is not one of these is refused, never drawn half."""

from __future__ import annotations

import math

MOST_ROWS = 5000            # rows of a table, or points, one query may answer with
CANDLE = ("open", "high", "low", "close")
DIM_TYPES = ("string", "number", "time")


class Bad(ValueError):
    """A frame that is not what it says it is."""


class TooMany(Bad):
    """A frame over its bound."""


def _number(v):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise Bad(f"{v!r} is not a number")
    return float(v) if math.isfinite(v) else None


def _list(v, what: str, most: int | None = None) -> list:
    most = MOST_ROWS if most is None else most
    if not isinstance(v, list):
        raise Bad(f"{what} is not a list")
    if len(v) > most:
        raise TooMany(f"{what} has {len(v)} entries, more than the {most} allowed")
    return v


def _on_grid(time: list, values: list, g) -> list:
    out: list = [None] * g.n
    for t, v in zip(time, values, strict=True):
        v = _number(v)
        if isinstance(t, int | float) and not isinstance(t, bool) and g.since - g.step < t <= g.until and v is not None:
            out[g.at(t + 1e-6 * g.step)] = v            # (as a list of series is placed)
    return out


def _series(f: dict, g, most_series: int) -> dict:
    time = _list(f.get("time"), "time", 100_000)
    every = _list(f.get("series"), "series", most_series)
    placed = []
    for s in every:
        if not isinstance(s, dict):
            raise Bad("a series is not a map")
        values = _list(s.get("values"), "a series' values", 100_000)
        if len(values) != len(time):
            raise Bad(f"series {s.get('key')!r} has {len(values)} values for {len(time)} times")
        placed.append((str(s.get("key", "")), s.get("role"), str(s.get("unit") or ""), _on_grid(time, values, g)))
    roles = {r: (k, u, v) for k, r, u, v in placed if r}
    base = {"times": g.times, "step": g.step, "capped": 0, "read_log": False, "shape": "series"}
    if set(roles) >= {"input", "output"}:
        (xk, xu, xv), (yk, yu, yv) = roles["input"], roles["output"]
        return {**base, "roles": ["input", "output"], "x": {"type": "query", "label": xk, "unit": xu, "scale": "number"},
                "series": [{"name": yk, "xs": xv, "values": yv, "times": g.times, "ids": None}], "unit": yu}
    if set(roles) >= set(CANDLE):
        return {**base, "roles": list(CANDLE), "unit": roles["close"][1], "series": [
            {"name": roles["close"][0], **{r: roles[r][2] for r in CANDLE}, "count": [None] * g.n}]}
    return {**base, "unit": placed[0][2] if placed and len({u for _, _, u, _ in placed}) == 1 else "",
            "series": [{"name": k, "values": v} for k, _, _, v in placed]}


def _maps(v, what: str, most: int) -> list[dict]:
    got = _list(v, what, most)
    if not all(isinstance(m, dict) for m in got):
        raise Bad(f"each of {what} is a map")
    return got


def _table(f: dict) -> dict:
    dims = [{"name": str(d.get("name", "")), "type": d.get("type")} for d in _maps(f.get("dims"), "dims", 4)]
    measures = [{"name": str(m.get("name", "")), "unit": str(m.get("unit") or "")} for m in _maps(f.get("measures"), "measures", 50)]
    if not dims or not measures or any(d["type"] not in DIM_TYPES for d in dims):
        raise Bad(f"a table needs a dim or more, each typed {', '.join(DIM_TYPES)}, and a measure or more")
    rows = []
    for r in _list(f.get("rows"), "rows"):
        if not isinstance(r, list) or len(r) != len(dims) + len(measures):
            raise Bad(f"a row holds {len(dims)} dims and {len(measures)} measures")
        keys = [str(v) if d["type"] == "string" else _number(v) for d, v in zip(dims, r, strict=False)]
        rows.append([*keys, *(_number(v) for v in r[len(dims):])])
    if len({tuple(r[:len(dims)]) for r in rows}) != len(rows):
        raise Bad("two rows share their dims' values: group them in the query")
    return {"shape": "table", "dims": dims, "measures": measures, "rows": rows, "unit": measures[0]["unit"],
            "capped": 0, "read_log": False}


def _points(f: dict) -> dict:
    x, y = f.get("x"), f.get("y")
    if not isinstance(x, dict) or not isinstance(y, dict):
        raise Bad("points need x and y, each {name, unit, values}")
    xs, ys = [_number(v) for v in _list(x.get("values"), "x")], [_number(v) for v in _list(y.get("values"), "y")]
    t = [_number(v) for v in _list(f["t"], "t")] if f.get("t") is not None else None
    group = [str(v) for v in _list(f["group"], "group")] if f.get("group") is not None else None
    if len(xs) != len(ys) or any(c is not None and len(c) != len(xs) for c in (t, group)):
        raise Bad("x, y, t and group must be of one length")
    keys = list(dict.fromkeys(group or [str(y.get("name", "y"))]))
    series = []
    for k in keys:
        at = [i for i in range(len(xs)) if group is None or group[i] == k]
        series.append({"name": k, "xs": [xs[i] for i in at], "values": [ys[i] for i in at],
                       "times": [t[i] for i in at] if t else None, "ids": None})
    out = {"shape": "points", "x": {"type": "field", "label": str(x.get("name", "x")), "unit": str(x.get("unit") or ""),
                                    "scale": "number"}, "series": series, "unit": str(y.get("unit") or ""),
           "capped": 0, "read_log": False}
    if f.get("order") == "time" and t:
        out["order"] = "time"
    return out


def _pairs(v, what: str) -> list[dict]:
    out = []
    for z in _list(v, what, 200):
        if not isinstance(z, list) or len(z) != 2 or None in (got := [_number(x) for x in z]):
            raise Bad(f"each of {what} is [re, im], two finite numbers")
        out.append({"re": got[0], "im": got[1]})
    return out


def _response(f: dict) -> dict:
    """How a system responds: ``frequency`` and, from a model, ``system`` (its form, numbers, poles and zeros, and the
    ``dt`` of the sampled model they belong to, if they do). ``supported: false`` with ``refused`` carries no curve."""
    fr, sy = f.get("frequency"), f.get("system")
    if not isinstance(fr, dict) or (sy is not None and not isinstance(sy, dict)):
        raise Bad("a response holds frequency: {hz, re, im, magnitude_db, phase_deg} and, from a model, system:")
    cols = ("hz", "re", "im", "magnitude_db", "phase_deg")
    freq = {k: [_number(v) for v in _list(fr.get(k), f"frequency.{k}")] for k in cols}
    if len({len(v) for v in freq.values()}) != 1:
        raise Bad(f"frequency's {', '.join(cols)} must be of one length")
    co = fr.get("coherence")
    freq["coherence"] = None if co is None else [_number(v) for v in _list(co, "frequency.coherence")]
    if f.get("supported") is False and freq["hz"]:
        raise Bad("a response refused carries no curve")
    out = {"shape": "response", "has": ["frequency", "system"] if sy is not None else ["frequency"], "frequency": freq,
           "unit": str(f.get("unit") or ""), "capped": 0, "read_log": False, "method": "model" if sy else "empirical",
           "samples": 0}
    if sy is not None:
        dt = _number(sy.get("dt"))
        out.update(system={k: (_number(sy[k]) if k != "form" else str(sy[k])) for k in ("form", "gain", "tau", "delay", "dt")
                           if sy.get(k) is not None},
                   poles=_pairs(sy.get("poles"), "system.poles"), zeros=_pairs(sy.get("zeros") or [], "system.zeros"),
                   domain="z" if dt else "s", delay_seconds=_number(sy.get("delay")) or 0.0, **({"dt": dt} if dt else {}))
    for k in ("path", "fit", "provenance", "process_from", "refused", "supported"):
        if f.get(k) is not None:
            out[k] = _plain(f[k], k)
    return out


def _plain(v, what: str, depth: int = 0):
    """What a response says of itself, as JSON can hold it: words, flags, finite numbers (any other number is None),
    and lists and maps of them two deep at most."""
    if v is None or isinstance(v, str | bool):
        return v
    if isinstance(v, int | float):
        return _number(v)
    if depth < 2 and isinstance(v, list):
        return [_plain(x, what, depth + 1) for x in _list(v, what, 200)]
    if depth < 2 and isinstance(v, dict) and len(v) <= 50:
        return {str(k): _plain(x, what, depth + 1) for k, x in v.items()}
    raise Bad(f"{what} holds {type(v).__name__}, or is nested too deep")


def answer(f: dict, g, most_series: int) -> dict:
    """The frame ``f`` drawn on the grid ``g``; ``Bad`` when it is not one of the frames above."""
    shape = f.get("shape")
    if shape == "response":
        return _response(f)
    if shape == "series":
        return _series(f, g, most_series)
    if shape == "table":
        return _table(f)
    if shape == "points":
        return _points(f)
    raise Bad(f"a data source answers a series, a table, points or a response, not {shape!r}")
