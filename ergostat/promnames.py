"""A model's own data in PromQL under its own names (SPEC §4b, *Names and labels in PromQL*): what the model declares
is a metric named for itself, and only the engine's own keep ``ergostat_``.

- a projection K: ``K_items{state, milestone}`` (a stock), ``K_transitions_total{from, to}`` (a flow),
  ``K_last_transition_timestamp_seconds{from, to}``, ``K_time_in_state_seconds`` (a histogram: ``_bucket{state, le}``,
  ``_sum``, ``_count``) and ``K_field_total{field}``, translated from the item index's tally as it is written
  (``item_labels``);
- a stock, flow or auxiliary P with readings (``sensor/P.S``): ``P``, with ``sensor="S"`` only when P has several
  sensors (its setting, ``set``, counted among them when a block sets it). A stock and a flow of one name write one
  series (``Sensor.series``), so they share one metric;
- a name is the model's with dashes as underscores. A part whose name another takes (a projection's metric) or that
  would read as the engine's (``ergostat_``) has its system prepended (``merging_gap_items``); one that still collides
  is refused at ``ergostat check`` (``clashes``), with the fix.

Labels stay bounded: a part's name is a metric, a sensor's a label value, both declared by the model; an item's id
never is either. A record written under the old generic names (``ergostat_sensor{part}``, ``ergostat_items{kind}``) is
still read (``Victoria._sel``), and a saved query that names them is read as the new names (``convert``)."""

from __future__ import annotations

import re

ENGINE = "ergostat_"
_WORD = re.compile(r"[^a-z0-9_]+")
ITEM = {"ergostat_items": "items", "ergostat_item_transitions_total": "transitions_total",
        "ergostat_item_last_transition_timestamp_seconds": "last_transition_timestamp_seconds",
        "ergostat_item_time_in_state_seconds_bucket": "time_in_state_seconds_bucket",
        "ergostat_item_time_in_state_seconds_sum": "time_in_state_seconds_sum",
        "ergostat_item_time_in_state_seconds_count": "time_in_state_seconds_count",
        "ergostat_item_lead_seconds_bucket": "lead_seconds_bucket", "ergostat_item_lead_seconds_sum": "lead_seconds_sum",
        "ergostat_item_lead_seconds_count": "lead_seconds_count",
        "ergostat_item_field_total": "field_total"}
_SUFFIXES = {*ITEM.values(), "time_in_state_seconds"}
_KINDS = {"valve": ("ergostat_valve_position", "valve"), "block": ("ergostat_block_output", "block")}
_MEASURES = {"run": "block", "observer": "observer"}       # kind/NAME/MEASURE: ergostat_<kind>_<measure>{<label>=NAME}


def word(s: str) -> str:
    """A name as PromQL takes it: lowercase, each run of anything else an underscore, never starting with a digit."""
    w = _WORD.sub("_", str(s).lower()).strip("_") or "x"
    return "_" + w if w[0].isdigit() else w


def engine(series: str) -> dict[str, str]:
    """The name and labels of a series of the engine's own (a run's measure, an observer's, a valve, a block's output)."""
    kind, _, rest = series.partition("/")
    if kind in _MEASURES and rest.count("/") == 1:
        name, measure = rest.split("/")
        return {"__name__": f"ergostat_{kind}_{word(measure)}", _MEASURES[kind]: name}
    if kind in _KINDS and rest:
        return {"__name__": _KINDS[kind][0], _KINDS[kind][1]: rest}
    if rest:
        return {"__name__": f"ergostat_{word(kind)}", "name": rest}
    return {"__name__": "ergostat_series", "name": series}


def item_labels(labels: dict) -> dict:
    """An item metric as the index tallies it (``ergostat_items{kind="gap", ...}``) under its kind's own name
    (``gap_items{...}``); the index's own counters, and anything else, as they are."""
    if labels.get("__name__") in ITEM and labels.get("kind"):
        return {"__name__": f"{word(labels['kind'])}_{ITEM[labels['__name__']]}",
                **{k: v for k, v in labels.items() if k not in ("__name__", "kind")}}
    return dict(labels)


class Names:
    """The metric of each part the model declares (``metric``), which parts label their sensors (``several``), and
    the parts whose name cannot be kept apart (``clashes``: ``(part, name, where)``)."""

    def __init__(self, spec=None):
        parts: dict[str, list] = {}
        for kind in ("stocks", "flows", "auxiliaries"):
            for n, x in (getattr(spec, kind, None) or {}).items():
                parts.setdefault(n, []).append(x)
        kinds = getattr(spec, "items", None) or {}
        taken = {f"{word(k)}_{s}" for k in kinds for s in _SUFFIXES}
        self.metric: dict[str, str] = {}
        self.clashes: list[tuple[str, str, object]] = [     # (a kind of the model's own that would read as the engine's)
            (k, f"{word(k)}_items", x) for k, x in kinds.items() if not k.startswith("ergostat.") and word(k).startswith(ENGINE)]
        self._kinds = len(self.clashes)                    # (the kinds' come first; the parts' after)
        later = []
        for n in sorted(parts):
            m = word(n)
            if m in taken or m.startswith(ENGINE):
                later.append(n)
            else:
                self.metric[n] = m
        used = taken | set(self.metric.values())
        for n in later:                                    # (its system prepended: only where needed)
            system = next((x.system for x in parts[n] if getattr(x, "system", None)), None)
            m = f"{word(system)}_{word(n)}" if system else ""
            if m and m not in used and not m.startswith(ENGINE):
                self.metric[n] = m
                used.add(m)
            else:
                self.metric[n] = word(n)
                self.clashes.append((n, word(n), parts[n][0]))
        set_ = {n for n in parts if n in (getattr(spec, "auxiliaries", None) or {}) and spec.setter_of(n) is not None}
        self.several = {n for n, xs in parts.items()
                        if len({s for x in xs for s in (getattr(x, "sensors", None) or {})} | ({"set"} if n in set_ else set())) > 1}

    def labels(self, series: str) -> dict[str, str]:
        """A series' metric name and labels (without ``project`` and ``series``). A part the model does not declare
        (gone from it, or no model) keeps its own name, and its sensor's as a label."""
        kind, _, rest = series.partition("/")
        if kind != "sensor" or not rest:
            return engine(series)
        part, dot, s = rest.rpartition(".")
        if not dot or not part:
            part, s = rest, ""
        name = self.metric.get(part) or word(part)
        return {"__name__": name, **({"sensor": s} if s and (part not in self.metric or part in self.several) else {})}

    def problems(self) -> list:
        from .spec.load import Problem
        return [Problem("error", f"projection {n}: its PromQL names ({m}, ...) would read as the engine's own "
                                 "(ergostat_): rename it" if i < self._kinds else
                        f"{n}: its PromQL name {m} is taken (a projection's metric, or ergostat_, the engine's own) and "
                        "no system of its own keeps it apart: rename it, or put it in a system",
                        getattr(x, "where", None), "metric-clash") for i, (n, m, x) in enumerate(self.clashes)]


_LAST: list = [None, None]


def names_for(spec) -> Names:
    """The model's names, worked out once per model (a reload is a new one)."""
    was, got = _LAST
    if was is not spec or got is None:
        got = Names(spec)
        _LAST[:] = [spec, got]
    return got


_OLD = re.compile(r'\b(ergostat_sensor|ergostat_items|ergostat_item_[a-z_]+)\s*\{([^{}]*)\}')
_EQ = re.compile(r'\s*([A-Za-z_]\w*)\s*=\s*"((?:[^"\\]|\\.)*)"\s*')


def _or_none(v: str) -> str:
    """A matcher value as a regex that takes it or the label's absence (``v|``)."""
    return re.sub(r"([.^$*+?()\[\]{}|])", r"\\\\\1", v) + "|"


def convert(text: str, names: Names, both: bool = False) -> tuple[str, list[str]]:
    """A query written over the old generic names, as the new ones: each ``ergostat_sensor{part="P", ...}`` and
    ``ergostat_item_...{kind="K", ...}`` selector whose part or kind is matched exactly. Returns the text and what was
    turned (``old -> new``); a selector without one (``sum by (kind) (ergostat_items)``) is left as written.
    ``both``: each selector asks the new name and the old (``{__name__=~"gap_items|ergostat_items",kind=~"gap|"}``), so
    a record still under the old names answers as before, and one under the new answers too."""
    said: list[str] = []

    def one(m):
        name, body = m[1], m[2]
        matchers = [x for x in body.split(",") if x.strip()]
        pairs = [_EQ.fullmatch(x) for x in matchers]
        key = "part" if name == "ergostat_sensor" else "kind"
        got = next((p for p in pairs if p and p[1] == key), None)
        if got is None or (name != "ergostat_sensor" and name not in ITEM and name + "_bucket" not in ITEM):
            return m[0]
        rest = [x.strip() for x, p in zip(matchers, pairs, strict=True) if p is not got]
        dropped = None                                      # (a single sensor's label: the new name has none)
        if name == "ergostat_sensor":
            new = names.labels(f"sensor/{got[2]}.x")["__name__"]
            if got[2] in names.metric and got[2] not in names.several:
                dropped = next((p for p in (_EQ.fullmatch(r) for r in rest) if p and p[1] == "sensor"), None)
                rest = [x for x, p in zip(rest, [_EQ.fullmatch(r) for r in rest], strict=True) if not (p and p[1] == "sensor")]
        else:
            new = f"{word(got[2])}_{ITEM.get(name) or ITEM[name + '_bucket'].removesuffix('_bucket')}"
        out = new + ("{" + ",".join(rest) + "}" if rest else "")
        said.append(f"{m[0]} -> {out}")
        if not both:
            return out
        either = [f'__name__=~"{new}|{name}"', f'{key}=~"{_or_none(got[2])}"',
                  *([f'sensor=~"{_or_none(dropped[2])}"'] if dropped else []), *rest]
        return "{" + ",".join(either) + "}"

    return _OLD.sub(one, text), said
