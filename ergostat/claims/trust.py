"""Trust as a measure (SPEC §12g): how far each block's claims hold, over the last ``WEEK`` of record.

``ergostat.trust.contradicted`` is the share of the claims checked (verified or contradicted) that were contradicted,
0 while none is; ``ergostat.trust.contradictions``, ``.verified``, ``.unchecked`` and ``.claims`` are counts. Each
is about every block, or, with ``@WHO``, one: ``@developer`` (a block), ``@rung:ai`` (every block on that rung),
``@model:haiku`` (every claim made by that model). A sensor reads one (``builtin:
ergostat.trust.contradicted@developer``) on a stock or an auxiliary, so a goal can hold it; ``ergostat claims``, the
MCP tool ``trust`` and the Items page's ``ergostat.claim`` section show them all, by block, by rung and by model."""

from __future__ import annotations

import time

from ..spec.ir import TRUST, TRUST_MEASURES
from . import record

WEEK = 7 * 86400.0
COUNTS = ("claims", "verified", "contradicted", "unchecked", "made")


def _who(c: dict, who: str | None) -> bool:
    if not who:
        return True
    if who.startswith("rung:"):
        return c.get("rung") == who[5:]
    if who.startswith("model:"):
        return (c.get("model") or "") == who[6:]
    return c.get("block") == who


def counts(claims, who: str | None = None) -> dict:
    out = {k: 0 for k in COUNTS}
    for c in claims:
        if _who(c, who):
            out["claims"] += 1
            out[c["state"]] = out.get(c["state"], 0) + 1
    checked = out["verified"] + out["contradicted"]
    out["checked"] = checked
    out["contradicted_share"] = out["contradicted"] / checked if checked else None
    return out


def table(p, since: float | None = None, now: float | None = None) -> dict:
    """Every block's, rung's and model's counts over the window (the last week by default), and the latest
    contradicted claims, newest first."""
    now = now or time.time()
    since = now - WEEK if since is None else since
    cs = list(record.stored(p, since=since, until=now).values())
    by = {"block": sorted({c.get("block") for c in cs if c.get("block")}),
          "rung": sorted({c.get("rung") for c in cs if c.get("rung")}),
          "model": sorted({c.get("model") for c in cs if c.get("model")})}
    rows = []
    for what, names in by.items():
        for n in names:
            who = n if what == "block" else f"{what}:{n}"
            rows.append({"by": what, "name": n, "who": who, **counts(cs, who)})
    bad = sorted((c for c in cs if c["state"] == "contradicted"), key=lambda c: -c.get("verdict_time", c["time"]))
    return {"since": since, "until": now, "all": counts(cs), "rows": rows,
            "contradicted": [{k: c.get(k) for k in ("id", "says", "about", "block", "kind", "why", "time", "session", "model")}
                             for c in bad[:20]]}


def measure(p, name: str, now: float | None = None) -> float:
    m = TRUST.match(name)
    if not m:
        raise ValueError(f"no measure {name!r}: {', '.join(TRUST_MEASURES)} (each with @WHO for one)")
    what, who = m.group(1), m.group(2)
    now = now or time.time()
    first = p.events.first_time() or now
    got = counts(record.stored(p, since=max(now - WEEK, first), until=now).values(), who)
    if what == "contradicted":
        return float(got["contradicted_share"] or 0.0)
    if what == "contradictions":
        return float(got["contradicted"])
    return float(got[what])
