"""The day's AI budget (SPEC §9.9): ``budget: {daily, max-cost}`` checked, which runs it charges, and the trailing day's
spend folded from the record by run id, never by lease state or by time order.

A run reserves before it starts (``reserve`` on its ``ergostat.lease.taken``, or on its ``agent.started`` when it is
not leased) and is charged, while its end is within the last 24 h, what it cost; until it ends, its reserve. What
cannot be known counts as the worst case: a missing or malformed cost is the run's reserve (``max-cost`` when it
reserved nothing), and a record that cannot be read is an error, never 0. Nothing is refused here: the permit is
``run-budget-permit``'s."""

from __future__ import annotations

import math
import time

from ..spec.ir import Budget

KEYS = ("daily", "max-cost")
DAILY_MAX = 10000.0                    # dollars a day: the ceiling on what config may let runs spend (lesson-4)
FREE_KINDS = ("person", "decision", "program", "rule")   # the allowlist: an agent of one of these, on a block not ai
STARTS, ENDS = "ergostat.lease.taken,agent.started", "agent.ran,agent.failed,budget.closed"
DAY, READ = 86400.0, 7 * 86400.0


def _number(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _bad(key: str, v, top: float, said: str) -> list[str]:
    x = _number(v)
    if x is None:
        return [f"budget.{key}: a number of US dollars, not {v!r}"]
    return [] if 0 < x <= top else [f"budget.{key}: more than 0 and at most {said}, not {x:g}"]   # NaN, inf: out of bounds


def check(daily, max_cost) -> list[str]:
    """What is wrong with these values, each its own sentence: run again at run time by the permit."""
    wrong = _bad("daily", daily, DAILY_MAX, f"{DAILY_MAX:g} (dollars over the trailing 24 h)")
    top, said = (DAILY_MAX, f"{DAILY_MAX:g}") if wrong else (float(daily), "budget.daily (what one run reserves)")
    return wrong + _bad("max-cost", max_cost, top, said)


def parse(raw) -> tuple[Budget | None, list[str]]:
    """``budget:`` as written: the Budget, or None and every error (an unknown key, a missing key, a non-number, a
    value out of bounds)."""
    if not isinstance(raw, dict):
        return None, ["budget: a map of daily: and max-cost: (US dollars)"]
    wrong = [f"budget: unknown key {k!r} (known: {', '.join(KEYS)})" for k in raw if k not in KEYS]
    wrong += [f"budget: {k}: is required" for k in KEYS if k not in raw]
    if "daily" in raw and "max-cost" in raw:
        wrong += check(raw["daily"], raw["max-cost"])
    elif "daily" in raw or "max-cost" in raw:
        k = "daily" if "daily" in raw else "max-cost"
        wrong += _bad(k, raw[k], DAILY_MAX, f"{DAILY_MAX:g}")
    return (None, wrong) if wrong else (Budget(float(raw["daily"]), float(raw["max-cost"])), [])


def free(spec, b) -> bool:
    """A run of this block costs the budget nothing only when the block is not ``ai`` and its agent is declared with a
    kind on the allowlist; every other run (no agent, an undeclared one, no kind, ai, narrow-ai) is charged."""
    a = spec.agents.get(b.agent) if b.agent else None
    return b.type != "ai" and a is not None and a.kind in FREE_KINDS


def _known(v) -> float | None:
    v = _number(v)
    return v if v is not None and math.isfinite(v) and v >= 0 else None


def cost_of(e: dict) -> float | None:
    """An end's cost in dollars when known (finite and at least 0); None when missing or malformed."""
    d = e.get("data") or {}
    ai = d.get("ai")
    return _known(ai.get("cost_usd") if isinstance(ai, dict) else d.get("cost_usd"))


def _charged(spec, blocks: set) -> bool:
    """A run is charged unless every block its events name is a declared, free block (no spec, no name: charged)."""
    found = [spec.blocks.get(n) if spec is not None and isinstance(n, str) else None for n in blocks]
    return not found or not all(b is not None and free(spec, b) for b in found)


def fold(p, budget: Budget, now: float | None = None, spec=None) -> dict:
    """The trailing day's spend: ``spent`` (ended runs' charges, the end within 24 h), ``reserved`` (runs not ended),
    and ``runs`` (run id → its charge; a free block's runs are left out, given ``spec``). Reads 7 days of starts and
    ends; a record that cannot be read raises. A ``budget.closed`` counts only when ergostat wrote it."""
    now = time.time() if now is None else now
    reserve: dict[str, float] = {}
    blocks: dict[str, set] = {}            # run id → the blocks its events name (lease: data.block; agent.*: item)
    for e in p.events.query(n=None, type=STARTS, since=now - READ):
        d = e.get("data") or {}
        leased = e["type"] == "ergostat.lease.taken"
        run = d.get("run") if leased else e.get("id")
        if run is None:
            continue
        blocks.setdefault(run, set()).add(d.get("block") if leased else e.get("item"))
        if not leased and "reserve" not in d:
            continue                       # an agent.started with no reserve: a leased run's (its lease reserved) or free
        r = _known(d.get("reserve"))
        reserve[run] = max(reserve.get(run, 0.0), budget.max_cost if r is None else r)
    ends: dict[str, list[float]] = {}
    for e in p.events.query(n=None, type=ENDS, since=now - READ):
        closed = e["type"] == "budget.closed"
        if closed and e.get("source") != "ergostat":
            continue                       # a block's output, `ergostat record` or a push may not release a reserve
        run = (e.get("data") or {}).get("run") if closed else e.get("causedby")
        if run is None:
            continue
        blocks.setdefault(run, set()).add((e.get("data") or {}).get("block") if closed else e.get("item"))
        got = ends.setdefault(run, [])     # ended, though perhaps more than a day ago: charged 0
        if e["time"] >= now - DAY:
            c = cost_of(e)
            got.append(c if c is not None else reserve.get(run, budget.max_cost))
    gone = {run for run, bs in blocks.items() if not _charged(spec, bs)}
    reserve = {run: r for run, r in reserve.items() if run not in gone}
    runs = {run: max(ends[run], default=0.0) for run in ends if run not in gone}
    spent = sum(runs.values())
    held = {run: r for run, r in reserve.items() if run not in ends}
    runs.update(held)
    return {"spent": spent, "reserved": sum(held.values()), "runs": runs}


def left(p, spec, now: float | None = None) -> float:
    """``ergostat.budget.left``: daily − spent − reserved. Raises when no budget: is declared or the record cannot be
    read, never daily or 0."""
    from ..numbers.measures import MeasureError
    b = getattr(spec, "budget", None) if spec is not None else None
    if b is None:
        raise MeasureError("no budget: is declared in ergostat.yaml (SPEC §9.9)")
    try:
        f = fold(p, b, now, spec)
    except Exception as e:
        raise MeasureError(f"the record cannot be read for the budget: {type(e).__name__}: {e}") from e
    return b.daily - f["spent"] - f["reserved"]
