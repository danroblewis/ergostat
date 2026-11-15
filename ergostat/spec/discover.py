"""``ergostat discover``: finding the model in what already exists.

- **From Prometheus** (``discover prometheus``): the series a Prometheus holds, read from its
  metadata, proposed as a draft model. A gauge is a level (a stock: a queue's depth, a disk's
  use); a counter is a flow (its rate per hour). A counter and a gauge that share a name's stem
  (``jobs_enqueued_total``, ``jobs_queue_depth``) are proposed as a flow into that stock. What is
  proposed is a draft to read, never written over the model.
- **From the record** (``discover loops``): for each flow of each measured stock, whether the
  flow's rate follows the stock's level after a delay. An outflow that rises after the stock
  rises (or an inflow that falls) is the signature of a balancing loop: something is acting on
  that stock. When nothing in the model sets that flow, it is a loop nobody wrote down, and it is
  proposed as a goal and an ``external`` block. A stock nothing responds to is a candidate for
  missing feedback."""

from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request

from ..durations import human
from .ir import Spec

LEVEL_WORDS = ("depth", "queue", "backlog", "pending", "inflight", "in_flight", "size", "bytes", "used", "usage", "length",
               "lag", "age", "outstanding", "waiting", "active", "open", "items", "messages", "jobs", "count", "ratio")
FLOW_SUFFIXES = ("_total", "_count", "_sum")


def _get(url: str, path: str, params: dict | None = None, timeout: float = 10) -> dict:
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    with urllib.request.urlopen(f"{url.rstrip('/')}{path}{q}", timeout=timeout) as r:   # noqa: S310
        body = json.loads(r.read().decode())
    if body.get("status") != "success":
        raise RuntimeError(body.get("error", "prometheus said no"))
    return body["data"]


def stem(name: str) -> str:
    n = name
    for suf in FLOW_SUFFIXES:
        n = n.removesuffix(suf)
    for w in ("_enqueued", "_dequeued", "_processed", "_received", "_sent", "_created", "_deleted", "_completed",
              "_failed", "_started", "_finished", "_in", "_out", "_added", "_removed", "_depth", "_size", "_length",
              "_pending", "_backlog", "_queue", "_bytes", "_used"):
        n = n.removesuffix(w)
    return n


def yaml_name(metric: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "-", metric.lower()).strip("-")
    return n if n and n[0].isalpha() else f"m-{n}"


OUT_WORDS = ("dequeued", "processed", "completed", "deleted", "sent", "removed", "out", "finished", "acked", "served")


def from_prometheus(url: str, match: str | None = None, limit: int = 60) -> tuple[str, list[str]]:
    """A draft model of what the Prometheus at ``url`` holds; and notes."""
    meta = _get(url, "/api/v1/metadata")
    rx = re.compile(match) if match else None
    gauges, counters = {}, {}
    for name, entries in sorted(meta.items()):
        if rx and not rx.search(name):
            continue
        t = (entries[0] or {}).get("type") if entries else None
        if t == "gauge" and any(w in name for w in LEVEL_WORDS):
            gauges[name] = entries[0].get("help", "")
        elif t == "counter":
            counters[name] = entries[0].get("help", "")
    notes = []
    if len(gauges) + len(counters) > limit:
        notes.append(f"{len(gauges) + len(counters)} series matched; the first {limit} are proposed (narrow with --match)")
    stocks, flows = {}, {}
    for g, help_ in list(gauges.items())[:limit]:
        n = yaml_name(g)
        stocks[n] = {"description": help_, "sensor": {"query": {"source": "prom", "promql": f"sum({g})"}, "every": "1m"}}
    for c, help_ in list(counters.items())[: max(0, limit - len(stocks))]:
        n = yaml_name(stem(c) + ("-out" if any(w in c for w in OUT_WORDS) else "-in"))
        while n in flows:
            n += "-x"
        f = {"description": help_, "sensor": {"query": {"source": "prom", "promql": f"sum(rate({c}[5m])) * 3600"},
                                              "every": "1m"}}
        st = next((s for g, s in ((g, yaml_name(g)) for g in gauges) if stem(g) == stem(c)), None)
        if st:
            f["from" if any(w in c for w in OUT_WORDS) else "to"] = st
        else:
            f["to"] = None
            notes.append(f"flow {n} ({c}): no gauge shares its stem; say which stock it fills or drains")
        flows[n] = f
    out = {"sources": {"prom": {"type": "prometheus", "url": url}}, "stocks": stocks, "flows": flows}
    import yaml

    from .convert import Dumper, spaced, whole
    text = yaml.dump(whole(out), Dumper=Dumper, sort_keys=False, default_flow_style=False, width=10_000)
    text = text.replace("    to: null\n", "    to:                # which stock?\n")
    head = (f"# A draft model from the Prometheus at {url}: {len(stocks)} stocks (gauges), {len(flows)} flows (counters,\n"
            f"# as rates per hour). Read it, keep what is real, add the goals you mean to hold.\n")
    if notes:
        head += "#\n" + "".join(f"#   - {x}\n" for x in notes)
    return head + "\n" + spaced(text), notes


# ---- loops in the record

def grid(pts: list[tuple[float, float]], t0: float, step: float, n: int) -> list[float | None]:
    """Each step's last value at or before it (a level, held)."""
    out, i, last = [], 0, None
    pts = sorted(pts)
    for k in range(n):
        t = t0 + (k + 1) * step
        while i < len(pts) and pts[i][0] <= t:
            last = pts[i][1]
            i += 1
        out.append(last)
    return out


def binned(events: list[tuple[float, float]], t0: float, step: float, n: int) -> list[float]:
    """Amounts summed per step, as a rate per hour."""
    out = [0.0] * n
    for t, a in events:
        k = int((t - t0) // step)
        if 0 <= k < n:
            out[k] += a
    return [x * 3600 / step for x in out]


def corr(a: list[float], b: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b, strict=False) if x is not None and y is not None]
    if len(pairs) < 8:
        return None
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    sx = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs))
    sy = math.sqrt(sum((y - my) ** 2 for _, y in pairs))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy)


def response(level: list, rate: list, max_lag: int) -> tuple[float, int] | None:
    """The strongest correlation of the rate with the level ``lag`` steps before, and that lag."""
    best = None
    for lag in range(0, max_lag + 1):
        c = corr(level[: len(level) - lag] if lag else level, rate[lag:])
        if c is not None and (best is None or abs(c) > abs(best[0])):
            best = (c, lag)
    return best


def loops(project, spec: Spec, window: float = 6 * 3600.0, steps: int = 120, now: float | None = None,
          threshold: float = 0.5) -> list[dict]:
    now = now or time.time()
    t0, step = now - window, window / steps
    ms, ev = project.measurements, project.events
    out = []
    for st in spec.stocks.values():
        pts = [p for s in st.sensors.values() for p in ms.range(s.series, t0, now)]
        if len(pts) < 8:
            continue
        level = grid(pts, t0, step, steps)
        responders = []
        for f in spec.flows_of(st.name):
            rpts = [p for s in f.sensors.values() for p in ms.range(s.series, t0, now)]
            if rpts:
                rate = [x if x is not None else 0.0 for x in grid(rpts, t0, step, steps)]
            else:
                opened = [(e["time"], e["data"].get("amount", 0.0)) for e in
                          ev.query(n=None, type="valve.opened", since=t0, until=now) if e["data"].get("flow") == f.name]
                if not opened:
                    continue
                rate = binned(opened, t0, step, steps)
            r = response(level, rate, max_lag=max(1, steps // 10))
            if r is None:
                continue
            c, lag = r
            drains = f.source == st.name
            balancing = (c > threshold and drains) or (c < -threshold and not drains)
            if not balancing:
                continue
            setter = spec.actuator_of(f.name)
            responders.append(f.name)
            out.append({"kind": "loop", "stock": st.name, "flow": f.name, "correlation": round(c, 2),
                        "delay": lag * step, "known": setter is not None, "set_by": setter.name if setter else None,
                        "says": (f"flow {f.name} {'rises' if drains else 'falls'} after stock {st.name} rises "
                                 f"(r={c:.2f}, after about {human(max(lag * step, step))}): a balancing loop acts here" +
                                 (f", the one through block {setter.name}" if setter else
                                  ", and nothing in the model sets this flow: a loop nobody wrote down"))})
        if not responders:
            goals = [g for g, x in spec.goals.items() if x.of.kind == "stock" and x.of.name == st.name]
            out.append({"kind": "unanswered", "stock": st.name, "goals": goals,
                        "says": f"nothing measured responds to stock {st.name}" +
                                (f" (goals: {', '.join(goals)})" if goals else "") +
                                ": no flow of it follows its level; if it matters, it lacks feedback"})
    return out


def proposal(found: list[dict], spec: Spec) -> str:
    """YAML for the loops nobody wrote down: a goal to state, and the external block that acts."""
    lines = []
    for f in found:
        if f["kind"] != "loop" or f["known"]:
            continue
        st = f["stock"]
        lines += [f"# {f['says']}", "goals:", f"  {st}-held:", f"    stock: {st}",
                  '    hold: "<= ?"                   # the level you mean it to hold', "blocks:",
                  f"  {st}-responder:", "    type: external                 # whatever already does this: name it",
                  f"    in: stock.{st}", f"    out: flow.{f['flow']}", ""]
    return "\n".join(lines)
