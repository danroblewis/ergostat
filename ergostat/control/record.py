"""A loop's signals as a control engineer reads them off the record: what its controller moves (u),
what its goal holds (y), the setpoint (r), on one grid of equal buckets, and the measured inputs
beside the path from u to y.

u is, in this order: the flows its valves move (each opening an amount at its moment, summed into a
rate per hour over each bucket), or the setting it steps (a stock moved by a two-way flow its block
sets: the loop closes through it, SPEC §12), read as a level. y is its goal's part, read as a level
(a stock, an auxiliary) or a rate (a flow). The grid is the reference window's (the last day of
record at most), in buckets no shorter than y's sensor reads, so a bucket holds a reading."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .. import series
from ..spec.ir import Ref, Spec

REFERENCE = 24 * 3600.0
MAX_POINTS = 1500
LEAST = 2.0                 # seconds: the shortest bucket


@dataclass
class Signals:
    goal: str
    y: str                          # stock.x / auxiliary.x / flow.x
    u: str | None                   # stock.setting or flow.valve
    how: str                        # "setting" or "valve"
    blocks: list[str]               # the blocks that move u (the actuator, or the controller that steps the setting)
    controllers: list[str]
    flow: str | None                # the flow that moves u (a setting's two-way flow) or u itself (a valve)
    period: float | None            # seconds between the controller's runs (its every), when it has one
    path: list[str]                 # the parts between u and y
    others: list[str]               # measured inputs beside the path
    known: str | None = None        # when the process from u to y is known from the model already, why
    limits: list = field(default_factory=lambda: [None, None])


def causes(spec: Spec, ref: str) -> list[str]:
    kind, _, name = ref.partition(".")
    if kind == "stock":
        return [f"flow.{f.name}" for f in spec.flows_of(name)]
    t = spec.measured(kind).get(name)
    if t is None:
        return []
    out = [str(Ref(r.kind, r.name)) for r in getattr(t, "driven_by", [])]
    eqn = getattr(t, "equation", None)
    if eqn is not None:
        out += [r for r in eqn.refs if r not in out]
    return out


def _ancestors(spec: Spec, ref: str, stop: set[str]) -> set[str]:
    seen, todo = set(), [ref]
    while todo:
        x = todo.pop()
        for c in causes(spec, x):
            if c not in seen and c not in stop:
                seen.add(c)
                todo.append(c)
    return seen


def _measured(spec: Spec, ref: str) -> bool:
    kind, _, name = ref.partition(".")
    t = spec.measured(kind).get(name)
    if t is None:
        return False
    return bool(t.sensors) or (kind == "auxiliary" and spec.setter_of(name) is not None) or \
        (kind == "flow" and spec.actuator_of(name) is not None)


def signals(spec: Spec, goal: str) -> Signals | None:
    """What a loop's controller moves and what its goal holds, read off the model."""
    g = spec.goals.get(goal)
    if g is None:
        return None
    lp = spec.loop(goal)
    y = f"{g.of.kind}.{g.of.name}"
    u = flow = None
    how = ""
    blocks: list[str] = []
    known = None
    limits: list = [None, None]
    if lp.valves:
        flow = lp.valves[0]
        u, how, blocks = f"flow.{flow}", "valve", list(lp.actuators)
        b = spec.actuator_of(flow)
        if b is not None:
            limits = [b.min if b.min is not None else 0.0, b.max]
        if g.of.kind == "stock" and len(lp.valves) == 1:
            known = (f"{flow} {'drains' if spec.flows[flow].source == g.of.name else 'fills'} {g.of.name} directly: "
                     "an integrator, 1/s, known from the model; only its dead time is not")
    else:
        for i, part in enumerate(lp.through):
            if part.startswith("stock.") and i and lp.through[i - 1].startswith("flow."):
                flow = lp.through[i - 1].split(".", 1)[1]
                b = spec.actuator_of(flow)
                if not spec.flows[flow].two_way or b is None:
                    break                          # the long way, through queues: no one setting it turns
                u, how, blocks = part, "setting", [b.name]
                break
    if u is None:
        return None
    period = None
    for n in [*blocks, *lp.controllers]:
        b = spec.blocks.get(n)
        if b is not None and b.every:
            period = float(b.every)
            break
    down = _ancestors(spec, y, {u})
    path = sorted(x for x in down if x != y and u in _ancestors(spec, x, set()))
    stop = {u, y, *path}
    others = sorted({c for x in [y, *path] for c in causes(spec, x) if c not in stop and _measured(spec, c)
                     and not c.startswith("flow.")})
    return Signals(goal, y, u, how, blocks, list(lp.controllers), flow, period, path, others, known, limits)


def _every(spec: Spec, ref: str) -> float | None:
    kind, _, name = ref.partition(".")
    t = spec.measured(kind).get(name)
    evs = [s.every for s in (t.sensors.values() if t else []) if s.every]
    return min(evs) if evs else None


def grid(p, sig: Signals, at: float | None = None, window: float | None = None) -> tuple[float, float, int]:
    until = at if at is not None else time.time()
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=None)
    since = until - (window or REFERENCE)
    if oldest and oldest > since:
        since = oldest
    span = max(until - since, 1.0)
    h = max((_every(p.model.spec, sig.y) or 2 * LEAST) / 2, LEAST, span / MAX_POINTS)     # half its sensor's period: θ to within it
    return since, until, max(2, int(span // h))


def read(p, sig: Signals, since: float, until: float, n: int) -> dict:
    """u, y, r, e and the other inputs on the grid, with each bucket's middle time."""
    m = p.model
    spec = m.spec
    ts = series.times(since, until, n)

    def values(ref: str):
        kind, _, name = ref.partition(".")
        if kind == "flow":
            got = series.rate(p, name, since, until, n, changes=False)
            return got[0] if got else [None] * n
        return series.level(p, name, since, until, n)
    y = values(sig.y)
    if sig.how == "valve":
        w = (until - since) / n
        moved = [0.0] * n
        valves = [v for v in m.valves if m.valves[v].flow in {f.split(".", 1)[1] for f in [sig.u]}]
        for v in valves:
            for e in p.events.query(n=None, type="valve.opened", item=v, since=since, until=until):
                k = min(n - 1, max(0, int((e["time"] - since) / w)))
                moved[k] += float(e["data"].get("amount", 1) or 0)
        u = [x / w * 3600.0 for x in moved]
    else:
        u = values(sig.u)
    g = spec.goals[sig.goal]
    r = float(g.hold.value)
    e = [None if v is None else r - v for v in y]
    others = {o: values(o) for o in sig.others}
    return {"t": ts, "h": (until - since) / n, "u": u, "y": y, "r": r, "e": e, "others": others,
            "since": since, "until": until}
