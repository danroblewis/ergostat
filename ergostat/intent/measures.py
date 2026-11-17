"""The intent judge's measures (SPEC §12i), over the last ``WEEK`` of record, each for every kind it judges or, with
``@KIND``, one: ``ergostat.intent.false-done@hypothesis``.

- ``false-done``: of the work **accepted**, the share the owner later found not done as meant (reopened, followed
  up, corrected): the judge's false-done rate, what got past it;
- ``false-done-tests``: what that rate would be had the tests alone decided: of the work that reached its judged
  state (its tests passed), the share found not done as meant, by the judge (held, not overruled) or by the owner
  after it was accepted;
- ``accepted``, ``reopened`` (of the accepted, found by the owner): counts;
- ``judged``, ``met``, ``unmet``, ``contradicted``, ``unjudged``, ``overruled``: the verdicts given; ``cost``: what the
  judge spent, in dollars.

A sensor reads one (``builtin: ergostat.intent.false-done``) on a stock or an auxiliary, so a goal can hold it."""

from __future__ import annotations

import time

from ..spec.ir import INTENT, INTENT_MEASURES, IntentKind, Spec
from . import outcomes, record

WEEK = 7 * 86400.0


def kinds_of(spec: Spec) -> dict[str, IntentKind]:
    out: dict[str, IntentKind] = {}
    for b in spec.blocks.values():
        if b.judge_mode == "intent":
            out.update(b.params["intent"].kinds)
    return out


def table(p, spec: Spec, since: float | None = None, now: float | None = None, kind: str | None = None) -> dict:
    """Every count and rate over the window (the last week by default), by kind and in all; the latest verdicts held."""
    now = time.time() if now is None else now
    since = now - WEEK if since is None else since
    kinds = kinds_of(spec)
    vs = record.stored(p, since=since, until=now)
    eps = outcomes.episodes(p, spec, kinds, since, now, vs)

    def score(kind_: str | None) -> dict:
        es = [e for e in eps if kind_ is None or e["kind"] == kind_]
        ws = [v for v in vs.values() if kind_ is None or v.get("kind") == kind_]
        acc = [e for e in es if e["accepted"]]
        found = [e for e in acc if e["found"]]
        bad = [e for e in es if e["held"] or e["found"]]
        given = [v for v in ws if v.get("verdict")]
        out = {"reached": len(es), "accepted": len(acc), "reopened": len(found),
               "false_done": len(found) / len(acc) if acc else None,
               "false_done_tests": len(bad) / len(es) if es else None,
               "judged": len(given), "cost": round(sum(float(v.get("cost_usd") or 0) for v in ws), 4)}
        for st in ("met", "unmet", "contradicted", "unjudged"):
            out[st] = sum(1 for v in given if v["verdict"] == st)
        out["overruled"] = sum(1 for v in ws if v["state"] == "overruled")
        out["missed"] = sum(1 for v in ws if v["state"] == "missed")
        return out
    names = [kind] if kind else sorted(kinds)
    held = sorted((v for v in vs.values() if v.get("verdict") in record.HELD), key=lambda v: -(v.get("verdict_time") or 0))
    return {"since": since, "until": now, "all": score(kind), "kinds": {k: score(k) for k in names},
            "held": [{k: v.get(k) for k in ("id", "work", "verdict", "why", "state", "mode", "model", "verdict_time")}
                     for v in held[:20]],
            "latest": [{k: v.get(k) for k in ("id", "work", "verdict", "why", "state", "mode", "model", "verdict_time",
                                              "cost_usd")}
                       for v in sorted(vs.values(), key=lambda v: -(v.get("verdict_time") or v["time"]))[:30]]}


def measure(p, name: str, now: float | None = None) -> float:
    m = INTENT.match(name)
    if not m:
        raise ValueError(f"no measure {name!r}: {', '.join(INTENT_MEASURES)} (each with @KIND for one kind)")
    what, kind = m.group(1), m.group(2)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        raise ValueError("the model is an ergostat.toml: the intent judge is a block of an ergostat.yaml")
    now = time.time() if now is None else now
    first = p.events.first_time() or now
    got = table(p, spec, since=max(now - WEEK, first), now=now, kind=kind)["all"]
    key = what.replace("-", "_")
    v = got.get(key)
    return float(v or 0.0)
