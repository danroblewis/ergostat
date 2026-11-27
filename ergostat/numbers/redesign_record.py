"""The record a redesign's scorecard reads, as a mark (SPEC §12e, *Redesign*): the judge scores a waiting redesign again
when the mark has moved since it was scored, never because its scoring is old, and writes a promoted one only on a
scorecard whose mark is the record's as it is.

The mark is model-wide, as the scorecard's coherence and fit are. It is an allowlist of what ``scorecard.score`` reads:

- ``seq``: the newest ``seq`` in ``p.events`` of (a) the events of the model's own kinds' items (``<kind>.*``, and the
  types each kind's ``on`` moves it by; ergostat's own kinds and a ``once`` template's are left out): what coherence's
  process window counts as moves; (b) ``agent.started``, ``agent.ran``, ``agent.failed`` and ``person.asked`` of the
  model's own blocks (not a ``once`` template's, so neither the judge's block nor the redesigner's): what says a block
  acted; (c) ``valve.opened`` of the valves on the model's own flows: what the replay counts as a flow they open.
- ``readings``: a hash of ``p.measurements.latest`` of every sensor series of the model's own stocks, flows and
  auxiliaries: what the fit replays. (A ``once`` template's parts are left out, here and in (c): the judge's own work
  moves them, and a redesign, held to its system, never changes them, so they replay alike in both models.)
- ``model``: the model it is scored against, as a hash of its dynamics, control and sensors (``version.whole``), its
  words, its units and its projections: what ``check``'s findings and craft notes read of it. A change of words the
  owner accepts leaves the version as it was (so the redesign is not carried) but moves this.

It is compared for equality only, never ordered and never held against a time. It does not use
``p.events.last_seq()``: the judge's own ``ergostat.model-change.*`` and ``model.*`` events, modelling requests, the
redesigner's ``ergostat.model.redesign-*`` events and the template blocks' runs all move that, and a mark that moved
with them would have every waiting redesign scored again on every pass. What it leaves out: an event a model block
writes under its own name that is neither an item's move nor its run's (its run's ``agent.ran`` says it acted)."""

from __future__ import annotations

from ..spec.ir import Spec, once_made

RESCORE_AFTER = 30 * 60.0     # a waiting redesign is scored again at most this often (s), whatever the record does
RESCORE_MOST = 1              # ... and at most this many a pass (first judgings and the write-path rescore aside)
RAN = "agent.started,agent.ran,agent.failed,person.asked"


class Unreadable(Exception):
    """The record's mark cannot be read: nothing is scored on it, and nothing written (it fails closed)."""


def read(p, spec: Spec) -> dict:
    """``mark``, or ``Unreadable`` with why."""
    try:
        return mark(p, spec)
    except Exception as e:
        raise Unreadable(f"its record's mark cannot be read ({type(e).__name__}: {e})") from e


def _newest(p, **k) -> int:
    got = p.events.query(n=1, **k)
    return int(got[-1]["seq"]) if got else 0


def mark(p, spec: Spec) -> dict:
    """The mark of the record the scorecard reads (above). Raises when the record cannot be read."""
    from . import version as ver
    kinds = [k for k, x in spec.items.items() if not k.startswith("ergostat.") and not once_made(spec, x)]
    types = sorted({f"{k}.*" for k in kinds} | {t for k in kinds for t in spec.items[k].on})
    seq = _newest(p, type=",".join(types)) if types else 0
    for b, x in spec.blocks.items():
        if not once_made(spec, x):
            seq = max(seq, _newest(p, type=RAN, item=b))
    for v in getattr(p.model, "valves", {}).values():
        if v.flow in spec.flows and not once_made(spec, spec.flows[v.flow]):
            seq = max(seq, _newest(p, type="valve.opened", item=v.name))
    series = sorted({s.series for t in (spec.stocks, spec.flows, spec.auxiliaries) for x in t.values()
                     if not once_made(spec, x) for s in x.sensors.values() if getattr(s, "series", None)})
    model = ver._hash([ver.whole(spec), ver.words(spec), ver.units(spec), ver.items(spec)])
    return {"seq": seq, "readings": ver._hash([[s, p.measurements.latest(s)] for s in series]), "model": model}


def due_for_rescore(stored: dict, now_mark: dict, now: float) -> list[dict]:
    """The passed redesigns to score again this pass, least recently scored first (by ``scored.seq``, then id), at most
    ``RESCORE_MOST``: one marked ``rescoring`` (carried, or its mark unreadable last time) at once; else one scored at
    least ``RESCORE_AFTER`` ago (or never stamped) on a record whose mark has moved since."""
    out = []
    for x in stored.values():
        if x.get("kind") != "redesign" or x.get("state") != "passed":
            continue
        s = x.get("scored") or {}
        if x.get("rescoring") or (now - float(s.get("at") or 0.0) >= RESCORE_AFTER and s.get("mark") != now_mark):
            out.append(x)
    return sorted(out, key=lambda x: ((x.get("scored") or {}).get("seq") or 0, x["id"]))[:RESCORE_MOST]
