"""What became of work after it said it was done (SPEC §12i): accepted, then found not done as meant, by the owner.

A piece of work **reaches its judged state** (``at``: the work says it is done, its tests passed) and is **accepted**
when it then enters one of its ``accepted`` states (merged, kept, closed). The owner **finds it not done as meant**
when, after accepting it and before it comes back to be judged again:

- it is **reopened** (``ergostat.item.reopened``, by the owner's hand or the owner's message, never by the judge);
- a **follow-up** is made of it from the owner's message (``ergostat.item.follow-up``, ``follows`` it);
- the owner **corrects** it: a correction (``ergostat.correction``) that names it (in ``corrects`` or its scope),
  proposed by the owner or confirmed by them.

Each moment of work reaching its judged state is an **episode**, scored once: judged held (the judge said unmet or
contradicted, and the owner did not overrule it), accepted, found by the owner. These are the intent measures."""

from __future__ import annotations

import re

from ..spec.ir import IntentKind, Spec
from ..spec.items import REOPENED

FOLLOW_UP = "ergostat.item.follow-up"
CORRECTION_PROPOSED = "ergostat.correction.proposed"
CORRECTION_CONFIRMED = "ergostat.correction.confirmed"


def judges(spec: Spec) -> set[str]:
    return {b.name for b in spec.blocks.values() if b.judge_mode == "intent"}


def signals(p, spec: Spec, since: float | None = None, until: float | None = None) -> dict[str, list[dict]]:
    """By item, each time the owner came back on it: ``{"time", "how", "event"}``, oldest first."""
    out: dict[str, list[dict]] = {}
    mine = judges(spec)
    for e in p.events.query(n=None, type=REOPENED, since=since, until=until):
        if e.get("source") in mine:
            continue
        out.setdefault(e["item"], []).append({"time": e["time"], "how": "reopened", "event": e})
    for e in p.events.query(n=None, type=FOLLOW_UP, since=since, until=until):
        f = (e.get("data") or {}).get("follows")
        if f:
            out.setdefault(str(f), []).append({"time": e["time"], "how": "followed up", "event": e})
    confirmed = {e["item"] for e in p.events.query(n=None, type=CORRECTION_CONFIRMED, since=since)}
    for e in p.events.query(n=None, type=CORRECTION_PROPOSED, since=since, until=until):
        if e.get("source") != "owner" and e["item"] not in confirmed:
            continue
        d = e.get("data") or {}
        text = " ".join([str(d.get("corrects") or ""), *[str(x) for x in d.get("scope") or []]])
        for it in set(re.findall(r"[a-z][a-z0-9_.-]*/[A-Za-z0-9_.:-]+", text)):
            out.setdefault(it.rstrip(".:,"), []).append({"time": e["time"], "how": "corrected", "event": e})
    for xs in out.values():
        xs.sort(key=lambda x: x["time"])
    return out


def accepted_at(it, kk: IntentKind, start: float, end: float | None = None) -> float | None:
    for m in it.moves:
        if m["time"] >= start and (end is None or m["time"] < end) and m.get("to") in kk.accepted:
            return m["time"]
    return None


def owner_found(p, spec: Spec, it, kk: IntentKind, start: float, end: float | None = None, sig=None) -> dict | None:
    """The owner's first coming back on work accepted after ``start`` (and before ``end``), or None."""
    ta = accepted_at(it, kk, start, end)
    if ta is None:
        return None
    xs = (sig if sig is not None else signals(p, spec, since=ta)).get(it.id) or []
    return next((x for x in xs if x["time"] >= ta and (end is None or x["time"] < end)), None)


def episodes(p, spec: Spec, kinds: dict[str, IntentKind], since: float, until: float, verdicts: dict) -> list[dict]:
    """Every moment of work reaching its judged state since then: what the judge said, whether it was accepted, and
    whether the owner found it not done as meant."""
    from ..spec import items as its
    by_entry = {(v["work"], v.get("entry_event")): v for v in verdicts.values()}
    sig = signals(p, spec, since=since)
    out = []
    for kk in kinds.values():
        if kk.kind not in spec.items:
            continue
        for it in its.project(p.events, spec, kk.kind):
            ins = [m for m in it.moves if m.get("to") == kk.at]
            for i, m in enumerate(ins):
                if not (since <= m["time"] <= until):
                    continue
                end = ins[i + 1]["time"] if i + 1 < len(ins) else None
                v = by_entry.get((it.id, m["event"]))
                st = (v or {}).get("verdict")
                overruled = (v or {}).get("state") == "overruled"
                found = owner_found(p, spec, it, kk, m["time"], end, sig)
                out.append({"work": it.id, "kind": kk.kind, "entered": m["time"], "verdict": st, "overruled": overruled,
                            "held": st in ("unmet", "contradicted") and not overruled,
                            "accepted": accepted_at(it, kk, m["time"], end) is not None,
                            "found": found["how"] if found else None, "verdict_id": (v or {}).get("id")})
    return out
