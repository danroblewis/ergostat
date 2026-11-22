"""Known controller laws (SPEC §12d, *Known laws*): the laws of controllers that ship with the systems they run in, each
with its typed, bounded parameters, declared on an external block (``law: {kind: kubernetes-hpa, target: 0.7, ...}``)
and made an ``extlaw.Law`` to step. Nothing is fitted here.

- **kubernetes-hpa**, the Horizontal Pod Autoscaler's rule: desired = ⌈replicas × metric / target⌉ when the ratio is
  outside ``tolerance``; a scale-down takes the largest desired over ``stabilize-down``, a scale-up the least over
  ``stabilize-up``; within [``min``, ``max``]; evaluated ``every``.
- **alert-rule**, a threshold alert (Prometheus's ``for``): fires (1) once its input is past ``threshold`` (``side``) for
  ``for``, resolves (0) as soon as it is back; the on-off family with levels 0 and 1, no hysteresis."""

from __future__ import annotations

import math
import re

from ..durations import DurationError, parse_duration
from ..numbers.extlaw import Law
from ..spec.ir import KnownLaw

REQUIRED = object()
DAY = 86400.0
# kind → parameter → (type, default, least, most); a number's least is exclusive where it is "above" (target > 0)
CATALOGUE: dict[str, dict[str, tuple]] = {
    "kubernetes-hpa": {
        "target": ("above", REQUIRED, 0.0, 1e12),        # the metric's target per replica
        "min": ("whole", REQUIRED, 1, 1_000_000),
        "max": ("whole", REQUIRED, 1, 1_000_000),
        "tolerance": ("number", 0.1, 0.0, 1.0),
        "stabilize-down": ("duration", 300.0, 0.0, 3600.0),
        "stabilize-up": ("duration", 0.0, 0.0, 3600.0),
        "every": ("duration", 15.0, 1.0, 3600.0),
    },
    "alert-rule": {
        "threshold": ("number", REQUIRED, -1e12, 1e12),
        "side": ("side", REQUIRED, None, None),
        "for": ("duration", REQUIRED, 0.0, 7 * DAY),
    },
}
ZERO = re.compile(r"^\s*0+(\.0+)?\s*(ms|s|m|h|d|w)?\s*$")


def _value(typ: str, v, lo, hi):
    """The value as its type reads it, or why not."""
    if typ == "side":
        return (v, "") if v in ("above", "below") else (None, "above or below")
    if typ == "duration":
        try:
            s = 0.0 if (isinstance(v, int | float) and not isinstance(v, bool) and v == 0) or \
                (isinstance(v, str) and ZERO.match(v)) else parse_duration(v)
        except DurationError:
            return None, "a duration (like 30s, 5m, 2h)"
        ok = lo <= s <= hi
        return (s, "") if ok else (None, f"a duration from {lo:g}s to {hi:g}s")
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        return None, "a number"
    if typ == "whole" and v != int(v):
        return None, f"a whole number from {lo:g} to {hi:g}"
    if typ == "above":
        return (float(v), "") if lo < v <= hi else (None, f"a number above {lo:g}, at most {hi:g}")
    return (float(v), "") if lo <= v <= hi else (None, f"a number from {lo:g} to {hi:g}")


def check(raw) -> tuple[KnownLaw | None, list[tuple[str | None, str]]]:
    """A declared law, checked: the law (None when any of it is wrong) and each wrong part, as (the key it is at, or
    None for the law as a whole; why)."""
    if not isinstance(raw, dict):
        return None, [(None, f"a map, {{kind: KIND, ...}}, KIND one of {', '.join(CATALOGUE)}")]
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in CATALOGUE:      # a list or map is no kind (and unhashable)
        return None, [("kind" if "kind" in raw else None, f"kind: one of {', '.join(CATALOGUE)}")]
    cat, got, bad = CATALOGUE[kind], {}, []
    for key in raw:
        if key != "kind" and key not in cat:
            bad.append((key, f"{kind} takes no {key}: (it takes {', '.join(cat)})"))
    for key, (typ, default, lo, hi) in cat.items():
        if key not in raw:
            if default is REQUIRED:
                bad.append((None, f"{kind} needs {key}:"))
            got[key] = default
            continue
        v, why = _value(typ, raw[key], lo, hi)
        if v is None:
            bad.append((key, f"{key}: {why}"))
        got[key] = v
    if not bad and kind == "kubernetes-hpa" and got["min"] > got["max"]:
        bad.append(("max", f"max: at least min ({got['min']:g})"))
    return (None if bad else KnownLaw(kind, got)), bad


def law(known: KnownLaw, dt: float | None = None) -> Law:
    """The law to step: an HPA on its own period (``every``), an alert rule on ``dt`` (its evaluation interval, 15s if
    not given)."""
    p = known.params
    if known.kind == "kubernetes-hpa":
        return Law("ratio", {"target": p["target"], "lo": p["min"], "hi": p["max"], "tolerance": p["tolerance"],
                             "stabilize_down": p["stabilize-down"], "stabilize_up": p["stabilize-up"]}, dt or p["every"])
    side = 1 if p["side"] == "above" else -1
    return Law("onoff", {"side": side, "on": p["threshold"], "off": p["threshold"], "for": p["for"], "for_off": 0.0,
                         "min_on": 0.0, "min_off": 0.0, "lo": 0.0, "hi": 1.0}, dt or 15.0)
