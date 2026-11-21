"""The measures a remote's box shows (SPEC §4c): which ones (``refs``), when their sensors last read here
(``read_times``), and each marked (``mark``) stale when the remote is not answering, or when its newest reading here
is older than ``readings``' bound (three of its sensor's periods, two minutes at least); a stale measure says how old
its last reading is, never the bare number. A part of the remote's show: here that it does not serve stays, missing."""

from __future__ import annotations

import time

from ..durations import human
from . import system_remote
from .readings import STALE_LEAST, STALE_RUNS


def _node(kind: str, name: str) -> str:
    return f"{'flow' if kind == 'flow' else 'stock'}:{name}"


def refs(spec, system: str, goals=None) -> list[str] | None:
    """The drawn parts (``stock:incidents-open``) a remote's box shows; None for a system that is not a remote's. The
    remote's own box: its ``show:`` here, else its top systems' served ``show:`` (both ``compose._shown``), else the
    goals it serves; never read, only its ``show:`` here. A system inside it: its served ``show:``, else its goals'.
    A stand-in goal is never one (``goals``: those with a loop drawn, else all)."""
    name = system_remote(spec, system)
    if name is None:
        return None
    r = spec.remotes[name]
    if system == name and r.get("show") is not None:
        return [x["part"] for x in r["show"]]
    if system != name and spec.show.get(system):
        return [_node(x.kind, x.name) for x in spec.show[system]]
    gone = {m["name"] for m in r.get("missing") or []}
    mine = sorted((len(spec.chain(g.system)), k) for k, g in spec.goals.items()
                  if (goals is None or k in goals) and system in spec.chain(g.system)
                  and f"goal.{k}" in (r.get("parts") or {}) and k not in gone)
    return [_node(spec.goals[k].of.kind, spec.goals[k].of.name) for _, k in mine][:5]


def _sensors(spec, part: str) -> list:
    kind, _, n = part.partition(":")
    got = spec.flows.get(n) if kind == "flow" else spec.stocks.get(n) or spec.auxiliaries.get(n)
    return list((getattr(got, "sensors", None) or {}).values())


def read_times(project, spec, at: float) -> dict:
    """When each sensor of a part shown on a remote's box last read here, at or before ``at`` (None: never)."""
    times = {}
    for s in spec.systems:
        for part in refs(spec, s) or []:
            for sen in _sensors(spec, part):
                got = project.measurements.latest(sen.series, at)
                times[sen.series] = got[0] if got else None
    return {"at": at, "times": times}


def mark(spec, box: dict, reads: dict | None) -> None:
    """Each measure on a remote's box (``fold.py``) marked ``stale`` (its value then how old its last reading is),
    ``missing`` (not served) or ``unchecked`` (never read). No reading time counts as never read."""
    r = spec.remotes[box["remote"]["name"]]
    flags = {x["part"]: x for x in r.get("show") or []} if box["label"] == box["remote"]["name"] else {}
    at = float((reads or {}).get("at") or time.time())
    times = (reads or {}).get("times") or {}
    down = box["remote"]["state"] != "ok"
    for m in box["measures"]:
        f = flags.get(m["part"]) or {}
        if f.get("missing") or f.get("unchecked"):
            m.update({"stale": True, "value": "not served" if f.get("missing") else "never read",
                      "missing" if f.get("missing") else "unchecked": True})
            continue
        sensors = _sensors(spec, m["part"])
        got = [(times.get(s.series), max(STALE_LEAST, STALE_RUNS * float(s.every or 0))) for s in sensors]
        newest = max((t for t, _ in got if t is not None), default=None)
        m["stale"] = down or bool(sensors) and not any(t is not None and at - t <= most for t, most in got)
        if m["stale"]:
            m["value"] = (f"last {m['value']} · {human(max(0.0, at - newest))} old" if newest is not None
                          else "never read" if down else "never read here")
