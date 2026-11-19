"""What runs cost, read back from the record: each run's numbers (on its ``agent.ran`` / ``agent.failed``), each
block's totals over a span and its history, the series each run adds (``run/BLOCK/cost_usd``, ``tokens``, ``cpu``,
``memory``, ``seconds``: plain metrics, beside the sensors'), and the built-in measures ``ergostat.cost.*`` (SPEC
§9.1):

- ``ergostat.cost.usd``: dollars the runs' AI sessions cost over the last day (reported, or estimated from tokens);
- ``ergostat.cost.tokens``: their tokens (input, output, cache reads and writes);
- ``ergostat.cost.cpu``: CPU seconds of the runs' process trees (user and system);
- ``ergostat.cost.memory``: the largest peak memory of a run, in MB;
- ``ergostat.cost.runs``: runs ended;

each over the last day, or with ``-hour`` the last hour (``ergostat.cost.usd-hour``); for every block, or with
``@BLOCK`` one block, ``@model:MODEL`` the runs whose sessions mostly used that model."""

from __future__ import annotations

import time

from ..spec.ir import COST

ENDS = "agent.ran,agent.failed"
SPANS = {"": 86400.0, "-hour": 3600.0}


def numbers(e: dict) -> dict:
    """One run's numbers, from its end event: time, cost (USD, None when not known), how the cost was known, tokens,
    CPU seconds, peak memory (bytes), wall seconds, exit, whether it failed, its model."""
    d = e.get("data") or {}
    ai = d.get("ai") if isinstance(d.get("ai"), dict) else None
    res = d.get("resources") if isinstance(d.get("resources"), dict) else {}
    cost = ai.get("cost_usd") if ai else d.get("cost_usd") if isinstance(d.get("cost_usd"), (int, float)) else None
    return {"time": e["time"], "run": e.get("causedby"), "cost_usd": cost,
            "cost": (ai.get("cost") if ai else "reported" if cost is not None else None),
            "tokens": int(((ai or {}).get("tokens") or {}).get("total") or 0), "model": (ai or {}).get("model"),
            "cpu": res.get("cpu"), "memory": res.get("memory_peak"), "seconds": d.get("seconds"), "exit": d.get("exit"),
            "failed": e["type"] == "agent.failed", "note": d.get("note")}


def write_series(p, block: str, data: dict, at: float | None = None) -> None:
    """The run's numbers as series of its block, so they are metrics like any other."""
    n = numbers({"type": "agent.ran", "time": at or time.time(), "data": data})
    rows = [(f"run/{block}/{k}", n["time"], float(v)) for k, v in
            (("cost_usd", n["cost_usd"]), ("tokens", n["tokens"] if data.get("ai") else None), ("cpu", n["cpu"]),
             ("memory", n["memory"] / 1e6 if n["memory"] else None), ("seconds", n["seconds"])) if v is not None]
    if rows:
        p.measurements.add_many(rows)


def ended(p, since: float, until: float, block: str | None = None) -> list[dict]:
    return p.events.query(n=None, type=ENDS, item=block, since=since, until=until, source="ergostat")


def totals(rows: list[dict]) -> dict:
    """Totals over runs' numbers: runs, failed, dollars (and how they were known), tokens, CPU, the largest peak memory,
    wall seconds."""
    costs = [r for r in rows if r["cost_usd"] is not None]
    hows = {r["cost"] for r in costs}
    how = None if not costs else hows.pop() if len(hows) == 1 else "partly estimated"
    mem = [r["memory"] for r in rows if r["memory"]]
    return {"runs": len(rows), "failed": sum(1 for r in rows if r["failed"]),
            "cost_usd": round(sum(r["cost_usd"] for r in costs), 6) if costs else None, "cost": how,
            "ai_runs": len(costs), "tokens": sum(r["tokens"] for r in rows),
            "cpu": round(sum(r["cpu"] or 0 for r in rows), 3) if any(r["cpu"] is not None for r in rows) else None,
            "memory_peak": max(mem) if mem else None, "seconds": round(sum(r["seconds"] or 0 for r in rows), 3)}


def per_block(p, since: float, until: float) -> dict[str, dict]:
    """Every block's totals over a span: one read of the record."""
    by: dict[str, list[dict]] = {}
    for e in ended(p, since, until):
        by.setdefault(e["item"], []).append(numbers(e))
    return {b: totals(rs) for b, rs in by.items()}


def hourly(rows: list[dict], since: float, until: float, key: str = "cost_usd") -> list[tuple[float, float]]:
    """A number summed into hours (the hour's start, its sum), over the span; hours with none are 0."""
    h0 = since // 3600 * 3600
    sums = {h0 + i * 3600: 0.0 for i in range(int((until - h0) // 3600) + 1)}
    for r in rows:
        if r.get(key) is not None:
            k = r["time"] // 3600 * 3600
            if k in sums:
                sums[k] += float(r[key])
    return sorted(sums.items())


def of_block(p, block: str, since: float, until: float, last: int = 200) -> dict:
    """One block's totals over a span, its runs' numbers (the newest ``last``) and its spending by hour."""
    rows = [numbers(e) for e in ended(p, since, until, block)]
    return {"since": since, "until": until, "totals": totals(rows), "runs": rows[-last:],
            "hourly": hourly(rows, since, until) if any(r["cost_usd"] is not None for r in rows) else []}


def measure(p, name: str, now: float | None = None) -> float:
    m = COST.match(name)
    if not m:
        from ..spec.ir import COST_MEASURES
        raise ValueError(f"no measure {name!r}: {', '.join(COST_MEASURES)} (each with -hour, and @BLOCK or @model:MODEL)")
    what, span, who = m.group(1), m.group(2) or "", m.group(3)
    now = now or time.time()
    block = None if not who or who.startswith("model:") else who
    rows = [numbers(e) for e in ended(p, now - SPANS[span], now, block)]
    if who and who.startswith("model:"):
        want = who[6:]
        rows = [r for r in rows if r["model"] and (r["model"] == want or want in r["model"])]
    t = totals(rows)
    if what == "usd":
        return float(t["cost_usd"] or 0.0)
    if what == "memory":
        return float((t["memory_peak"] or 0) / 1e6)
    return float(t[{"tokens": "tokens", "cpu": "cpu", "runs": "runs"}[what]] or 0.0)
