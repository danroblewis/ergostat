"""The leases on items, as measures (SPEC §9.5): ``ergostat.leases.*``, each narrowed to one kind or one block by
``@NAME``. ``held``, ``dead`` and ``overdue`` are levels, now; ``expired`` counts the expiries over the last day. A
sensor reads one (``builtin: ergostat.leases.expired``) on a stock or an auxiliary, so a goal can hold it: the
watchdog loop, drawn."""

from __future__ import annotations

import time

from ..spec import items as its
from ..spec.ir import DEAD, LEASES, Spec, own_kind
from . import EXPIRED
from .fold import held

DAY = 86400.0


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
    for kind in _kinds(spec, who):
        for it in its.project(p.events, spec, kind, until=now, transcript=False):
            lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else None
            if lease is None or (by_block and lease.get("block") != who):
                continue
            if held(it.fields):
                out["held"] += 1
                out["overdue"] += now > float(lease.get("expires") or 0)
            elif it.state == DEAD:
                out["dead"] += 1
    kinds = set(_kinds(spec, who))
    for e in p.events.query(n=None, type=EXPIRED, since=now - DAY, until=now):
        if by_block and (e.get("data") or {}).get("block") != who:
            continue
        k = its.kind_of(spec, e.get("item") or "")
        if k is not None and k.name in kinds:
            out["expired"] += 1
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
    for kind in _kinds(spec, None):
        for it in its.project(p.events, spec, kind, until=now, transcript=False):
            lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else None
            if lease is None or it.state != DEAD:
                continue
            last = (lease.get("history") or [{}])[-1]
            out.append({"item": it.id, "what": "dead", "attempts": lease.get("attempts"), "block": lease.get("block"),
                        "time": lease.get("dead") or it.entered, "how": last.get("how"), "why": last.get("why")})
    dead = {x["item"] for x in out}
    for e in p.events.query(n=200, type=EXPIRED, since=now - 3600, until=now):
        d = e.get("data") or {}
        if e["item"] in dead:                         # said once: a dead letter
            continue
        out.append({"item": e["item"], "what": "expired", "block": d.get("block"), "time": e["time"],
                    "silent": d.get("silent"), "fence": d.get("fence")})
    return sorted(out, key=lambda x: -float(x.get("time") or 0))[:20]
