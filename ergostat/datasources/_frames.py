"""A data source's typed answer (SPEC §4e, *Result shapes*), made into what a panel draws. A type's ``query`` may answer
with a frame instead of a list of series:

- ``{"shape": "series", "time": [...], "series": [{"key", "unit"?, "role"?, "values": [...]}]}``: values at those times,
  placed on the panel's grid as a list of series is. Roles ``input`` and ``output`` make two signals, drawn one against
  the other; ``open``, ``high``, ``low`` and ``close`` make one series of candles. Any other role (a loop's ``sp``,
  ``pv``, ``op``, ``mv``, limits, ``mode``) stays on its series, and ``roles`` lists them; one role is one series'.
- ``{"shape": "table", "dims": [{"name", "type"}], "measures": [{"name", "unit"?}], "rows": [[...], ...]}``: a dim is
  a ``string``, ``number`` or ``time``; a row holds its dims' values, then its measures' numbers.
- ``{"shape": "points", "x": {"name", "unit"?, "values"}, "y": {...}, "t"?: [...], "order"?: "time", "group"?: [...]}``.
- ``{"shape": "distribution", "name"?, "buckets": [{"labels": {"le": "0.5", ...}, "time": [...], "values": [...]}]}``:
  one histogram's cumulative buckets (Prometheus's ``_bucket`` by ``le``), made a distribution of ``bins`` with
  ``over_time``, the count in each bucket at each time.
- ``{"shape": "graph", "kind", "nodes", "edges", "semantics", "time", "omitted"}``: a diagram of one named kind
  (the catalog's §2.2); every edge's ends are nodes, ``paths_real`` is said, and ``acyclic`` is worked out here.
- ``{"shape": "response", "frequency": {"hz", "re", "im", "magnitude_db", "phase_deg", "coherence"?}, "system"?: {"form",
  "gain", "tau", "delay", "poles": [[re, im]], "zeros": [...], "dt"?}, "path"?, "fit"?, "provenance"?}``: how a system
  responds; a model's carries ``system``, and its poles are the sampled model's at ``dt`` when it has one.

A role on a series, or on a graph's field, is one of a closed list. Whatever the type, a frame is checked and bounded
here; one that is not one of these is refused, never drawn half."""

from __future__ import annotations

import math

MOST_ROWS = 5000            # rows of a table, points, a graph's nodes or its edges, one query may answer with
CANDLE = ("open", "high", "low", "close")
DIM_TYPES = ("string", "number", "time")
ROLES = ("sp", "pv", "op", "mv", "limit_hi", "limit_lo", "mode", "input", "output", *CANDLE)
KINDS = ("process", "conformance", "dependency", "wait_for", "impact", "service", "sequence", "lineage")
FIELD_ROLES = ("rate", "errors", "latency", "utilisation", "wait", "count", "age", "slack", "exposure")
EVIDENCE = ("observed", "declared", "both", "inferred", "simulated")
TIME_MODES = ("snapshot", "window", "frames", "events")
HEALTH = ("ok", "unhealthy")      # a node's, when it is known: one unhealthy member marks its group (query/graphfit.py)


class Bad(ValueError):
    """A frame that is not what it says it is; ``code``, the verdict's reason when it is a named misuse."""

    def __init__(self, words: str, code: str | None = None):
        super().__init__(words)
        self.code = code


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
        if s.get("role") is not None and s["role"] not in ROLES:
            raise Bad(f"series {s.get('key')!r} has the role {s['role']!r}; a role is one of {', '.join(ROLES)}")
        placed.append((str(s.get("key", "")), s.get("role"), str(s.get("unit") or ""), _on_grid(time, values, g)))
    roles = {r: (k, u, v) for k, r, u, v in placed if r}
    if len(roles) < sum(1 for _, r, _, _ in placed if r):
        twice = next(r for r in roles if sum(1 for _, x, _, _ in placed if x == r) > 1)
        raise Bad(f"two series have the role {twice!r}; a role is one series' (give each loop its own query)")
    base = {"times": g.times, "step": g.step, "capped": 0, "read_log": False, "shape": "series"}
    if set(roles) >= {"input", "output"}:
        (xk, xu, xv), (yk, yu, yv) = roles["input"], roles["output"]
        return {**base, "roles": ["input", "output"], "x": {"type": "query", "label": xk, "unit": xu, "scale": "number"},
                "series": [{"name": yk, "xs": xv, "values": yv, "times": g.times, "ids": None}], "unit": yu}
    if set(roles) >= set(CANDLE):
        return {**base, "roles": list(CANDLE), "unit": roles["close"][1], "series": [
            {"name": roles["close"][0], **{r: roles[r][2] for r in CANDLE}, "count": [None] * g.n}]}
    return {**base, "unit": placed[0][2] if placed and len({u for _, _, u, _ in placed}) == 1 else "",
            **({"roles": [r for _, r, _, _ in placed if r]} if roles else {}),
            "series": [{"name": k, "values": v, **({"role": r} if r else {})} for k, r, _, v in placed]}


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


def _bound(le) -> float:
    try:
        v = float(le)
    except (TypeError, ValueError, OverflowError):
        raise Bad(f"a bucket's le is {le!r}, not a number") from None
    if math.isnan(v):
        raise Bad("a bucket's le is NaN")
    return v


def _buckets(f: dict, g, most_series: int) -> dict:
    """One histogram's cumulative buckets made into the count in each bucket at each time of ``g``, and over the window.
    Refused: buckets of more than one histogram, or counts that fall from one bound to a higher one (so they are not
    one histogram's cumulative counts at one time). Warned: what lies above the highest finite bound."""
    every = _maps(f.get("buckets"), "buckets", most_series)
    labels = [b.get("labels") if isinstance(b.get("labels"), dict) else {} for b in every]
    if any("le" not in x for x in labels):
        raise Bad("each bucket needs its le label")
    rest = {tuple(sorted((k, str(v)) for k, v in x.items() if k not in ("le", "__name__"))) for x in labels}
    bounds = [_bound(x["le"]) for x in labels]
    if len(rest) > 1 or len(set(bounds)) != len(bounds):
        raise Bad(f"the buckets are of {max(len(rest), 2)} histograms, not one", "many-histograms")
    if not every:
        raise Bad("a histogram needs its buckets")
    placed = sorted((le, _on_grid(_list(b.get("time"), "time", 100_000), _list(b.get("values"), "values", 100_000), g))
                    for le, b in zip(bounds, every, strict=True))
    les = [le for le, _ in placed]
    finite = [le for le in les if math.isfinite(le)]
    if not finite or les[0] <= 0:
        raise Bad("a histogram's bounds are above 0 (its first bucket is drawn from 0), with a finite one at least")
    columns, above = [], 0.0
    for t in range(g.n):
        cum = [v[t] for _, v in placed]
        if any(c is None for c in cum):
            columns.append(None)                    # (a time some bucket has no value at: a gap, never a zero)
            continue
        for i, c in enumerate(cum):
            below = cum[i - 1] if i else 0.0
            if c < below - 1e-9 * max(1.0, abs(below)):
                raise Bad(f"at {g.times[t]:.0f} the count up to le={les[i]:g} ({c:g}) is below "
                          + (f"the count up to le={les[i - 1]:g} ({below:g})" if i else "zero"), "not-cumulative")
        columns.append([max(0.0, c - (cum[i - 1] if i else 0.0)) for i, c in enumerate(cum[:len(finite)])])
        above += cum[-1] - cum[len(finite) - 1] if len(finite) < len(cum) else 0.0
    counts = [sum(c[i] for c in columns if c) for i in range(len(finite))]
    total = sum(counts) + above
    top = f"le={finite[-1]:g}"
    warned = ([("open-top-bucket", f"{above:g} of {total:g} are above the highest bound ({top}), and are not drawn")]
              if above > 0 else [] if len(finite) < len(placed)
              else [("open-top-bucket", f"the buckets have no +Inf, so what lies above {top} is not known")])
    name, edges = str(f.get("name") or ""), [0.0, *finite]
    return {"shape": "distribution", "form": "bins", "unit": "", "times": g.times, "step": g.step, "capped": 0,
            "read_log": False, "x": {"type": "bins", "label": name, "unit": str(f.get("unit") or ""), "scale": "number",
                                     "edges": edges},
            "series": [{"name": name or "count", "xs": [(a + b) / 2 for a, b in zip(edges, edges[1:], strict=False)],
                        "values": counts}], "over_time": {"times": g.times, "counts": columns},
            "warnings": warned}


def _column(m: dict, key: str, n: int, what: str, need: bool = True) -> list | None:
    v = m.get(key)
    if v is None and not need:
        return None
    got = _list(v, f"{what}.{key}")
    if len(got) != n:
        raise Bad(f"{what}.{key} has {len(got)} entries for {n} {what}")
    return got


def _fields(m: dict, n: int, what: str) -> list[dict]:
    out = []
    for x in _maps(m.get("fields") or [], f"{what}.fields", 20):
        if x.get("role") is not None and x["role"] not in FIELD_ROLES:
            raise Bad(f"{what} field {x.get('name')!r} has the role {x['role']!r}; a role is one of {', '.join(FIELD_ROLES)}")
        out.append({"name": str(x.get("name", "")), "unit": str(x.get("unit") or ""), "role": x.get("role"),
                    "values": [_number(v) for v in _column(x, "values", n, what)]})
    return out


def _acyclic(ids: list, source: list, target: list) -> bool:
    """No directed cycle (a self-loop is one): Kahn's order reaches every node."""
    into, out = dict.fromkeys(ids, 0), {i: [] for i in ids}
    for a, b in zip(source, target, strict=True):
        into[b] += 1
        out[a].append(b)
    ready, seen = [i for i in ids if not into[i]], 0
    while ready:
        seen += 1
        for b in out[ready.pop()]:
            into[b] -= 1
            if not into[b]:
                ready.append(b)
    return seen == len(ids)


def _graph(f: dict) -> dict:
    kind, nodes, edges = f.get("kind"), f.get("nodes"), f.get("edges")
    if kind not in KINDS:
        raise Bad(f"a graph's kind is one of {', '.join(KINDS)}, not {kind!r}")
    if not isinstance(nodes, dict) or not isinstance(edges, dict):
        raise Bad("a graph needs nodes and edges, each a map of columns")
    ids = [str(i) for i in _list(nodes.get("id"), "nodes.id")]
    n = len(ids)
    if len(set(ids)) != n:
        raise Bad("two nodes share an id")
    node = {"id": ids, "label": [str(x) for x in _column(nodes, "label", n, "nodes")], "fields": _fields(nodes, n, "nodes")}
    for key in ("type", "group", "parent", "health"):
        if (col := _column(nodes, key, n, "nodes", need=False)) is not None:
            node[key] = [None if x is None else str(x) for x in col]
    if bad := next((x for x in node.get("health") or () if x not in (None, *HEALTH)), None):
        raise Bad(f"a node's health is one of {', '.join(HEALTH)}, not {bad!r}")
    eids = [str(i) for i in _list(edges.get("id"), "edges.id")]
    m = len(eids)
    edge = {"id": eids, **{k: [str(x) for x in _column(edges, k, m, "edges")] for k in ("source", "target", "relation", "evidence")}}
    known = set(ids)
    if len(set(eids)) != m:
        raise Bad("two edges share an id")
    if lost := next((x for x in [*edge["source"], *edge["target"], *(node.get("parent") or ())] if x is not None and x not in known), None):
        raise Bad(f"an edge or a parent names {lost!r}, which is not one of the nodes")
    if bad := next((e for e in edge["evidence"] if e not in EVIDENCE), None):
        raise Bad(f"an edge's evidence is one of {', '.join(EVIDENCE)}, not {bad!r}")
    inferred = "inferred" in edge["evidence"]
    if inferred and kind in ("wait_for", "dependency"):
        raise Bad(f"a {kind} graph is not built from inferred edges (correlation is not a dependency)")
    for key in ("n", "first_seen", "last_seen", "t", "confidence"):
        if (col := _column(edges, key, m, "edges", need=key == "confidence" and inferred)) is not None:
            edge[key] = [_number(v) for v in col]
    edge["fields"] = _fields(edges, m, "edges")
    sem, when, omitted = f.get("semantics"), f.get("time"), f.get("omitted")
    if not isinstance(sem, dict) or not isinstance(sem.get("paths_real"), bool):
        raise Bad("a graph says whether a route through two edges is evidence: semantics.paths_real, true or false")
    if not isinstance(when, dict) or when.get("mode") not in TIME_MODES:
        raise Bad(f"a graph's time.mode is one of {', '.join(TIME_MODES)}")
    if when["mode"] == "events" and "t" not in edge:
        raise Bad("a graph of events needs each edge's time, edges.t")
    if not isinstance(omitted, dict) or not all(k in omitted for k in ("nodes", "edges", "weight_share", "how")):
        raise Bad("a graph says what it left out: omitted.nodes, edges, weight_share and how (0, 0, 0, '' if nothing)")
    acyclic = _acyclic(ids, edge["source"], edge["target"])
    if sem.get("acyclic") is not None and sem["acyclic"] is not acyclic:
        raise Bad(f"the graph says acyclic is {sem['acyclic']}, but it {'has no' if acyclic else 'has a'} cycle")
    focus = [str(x) for x in sem.get("focus") or [] if str(x) in known]
    return {"shape": "graph", "kind": kind, "nodes": node, "edges": edge, "unit": "", "capped": 0, "read_log": False,
            "semantics": {"paths_real": sem["paths_real"], "acyclic": acyclic, "focus": focus},
            "time": {k: when.get(k) for k in ("mode", "since", "until", "as_of")},
            "omitted": {k: omitted[k] for k in ("nodes", "edges", "weight_share", "how")}}


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
    if shape == "distribution":
        return _buckets(f, g, most_series)
    if shape == "graph":
        return _graph(f)
    raise Bad(f"a data source answers a series, a table, points, a response, a histogram's buckets or a graph, not {shape!r}")
