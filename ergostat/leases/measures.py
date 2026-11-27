"""The leases on items, as measures (SPEC §9.5): ``ergostat.leases.*``, each narrowed to one projection or one block by
``@NAME``. ``held``, ``dead`` and ``overdue`` are levels, now; ``expired`` counts the expiries over the last day. A
sensor reads one (``builtin: ergostat.leases.expired``) on a stock or an auxiliary, so a goal can hold it: the
watchdog loop, drawn."""

from __future__ import annotations

import time

from ..spec import items as its
from ..spec.ir import DEAD, LEASES, Spec, own_kind
from . import EXPIRED
from .fold import held, refused_expiries

DAY = 86400.0


def query(p, type: str, **kw) -> list[dict]:
    """``projections.query`` (imported here: it imports this package's EXPIRED)."""
    from ..spec import projections
    return projections.query(p, type, **kw)


def _kinds(spec: Spec, who: str | None) -> list[str]:
    own = [k for k in spec.items if own_kind(k)]
    if who in spec.items:
        return [who]
    if who in spec.blocks and spec.blocks[who].takes:
        return [spec.blocks[who].takes.kind]
    return own


def counts(p, spec: Spec, who: str | None = None, now: float | None = None) -> dict[str, float]:
    now = time.time() if now is None else now
    by_block = who in spec.blocks and who not in spec.items
    out = {"held": 0, "dead": 0, "overdue": 0, "expired": 0}
    seen: dict = {}
    for kind in _kinds(spec, who):
        for it in its.project(p.events, spec, kind, until=now, transcript=False):
            seen[it.id] = it
            lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else None
            if lease is None or (by_block and lease.get("block") != who):
                continue
            if held(it.fields):
                out["held"] += 1
                out["overdue"] += now > float(lease.get("expires") or 0)
            elif it.state == DEAD:
                out["dead"] += 1
    kinds = set(_kinds(spec, who))
    evs = [e for e in query(p, EXPIRED, n=None, since=now - DAY, until=now)
           if not (by_block and (e.get("data") or {}).get("block") != who)
           and (k := its.kind_of(spec, e.get("item") or "")) is not None and k.name in kinds]
    void = refused_expiries(p.events, spec, evs, items=seen)      # (the items just projected: none folded again)
    out["expired"] = sum(1 for e in evs if e["id"] not in void)
    return {k: float(v) for k, v in out.items()}


def measure(p, spec: Spec, name: str, now: float | None = None) -> float:
    m = LEASES.match(name)
    if not m:
        raise ValueError(f"no measure {name!r}: ergostat.leases.held, expired, dead or overdue, with @KIND or @BLOCK")
    return counts(p, spec, m.group(2), now)[m.group(1)]


def attention(p, spec: Spec, now: float | None = None) -> list[dict]:
    """What needs the owner (SPEC §9.5): every dead letter, and every lease that expired over the last hour."""
    now = time.time() if now is None else now
    out = []
    for kind in _kinds(spec, None):                   # (its dead items alone, the latest first, as ``project`` has them)
        for it in sorted(its.in_states(p.events, spec, kind, [DEAD], until=now, items=True, transcript=False)[2],
                         key=lambda i: -i.last):
            lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else None
            if lease is None or it.state != DEAD:
                continue
            last = (lease.get("history") or [{}])[-1]
            out.append({"item": it.id, "what": "dead", "attempts": lease.get("attempts"), "block": lease.get("block"),
                        "time": lease.get("dead") or it.entered, "how": last.get("how"), "why": last.get("why")})
    dead = {x["item"] for x in out}
    evs = query(p, EXPIRED, n=200, since=now - 3600, until=now)
    void = refused_expiries(p.events, spec, evs)
    for e in evs:
        d = e.get("data") or {}
        if e["item"] in dead or e["id"] in void:      # said once: a dead letter (and a refused expiry is none)
            continue
        out.append({"item": e["item"], "what": "expired", "block": d.get("block"), "time": e["time"],
                    "silent": d.get("silent"), "fence": d.get("fence")})
    return sorted(out, key=lambda x: -float(x.get("time") or 0))[:20]
