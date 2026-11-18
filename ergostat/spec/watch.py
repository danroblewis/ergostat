"""Findings that need the record (SPEC §12): what a model that compiles cannot show until it has
run. A stock heading for its limit, a block saturating, a goal off that nothing answers, a person
who was asked and has not answered, a sensor gone quiet, and a critical goal decaying (answering
more slowly than it did, saturating more often, or owned by nobody), a block whose claims the record
contradicts, and a part the record has not exercised (it never moved, or held one value: its rate cannot be
identified yet, which is not evidence it is absent)."""

from __future__ import annotations

import time

from ..durations import human
from .ir import Spec
from .load import Problem

WINDOW = 6 * 3600.0
PERSON_WAIT = 3600.0
HORIZON = 7 * 86400.0


def slope(pts: list[tuple[float, float]]) -> float | None:
    """Least-squares change per second; None with too few points."""
    if len(pts) < 3:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    mv = sum(v for _, v in pts) / n
    den = sum((t - mt) ** 2 for t, _ in pts)
    return None if den == 0 else sum((t - mt) * (v - mv) for t, v in pts) / den


def recoveries(events: list[dict]) -> list[float]:
    """How long each time off lasted: from loop.off to the next loop.holding."""
    out, off = [], None
    for e in events:
        if e["type"] == "loop.off":
            off = e["time"]
        elif e["type"] == "loop.holding" and off is not None:
            out.append(e["time"] - off)
            off = None
    return out


def find(project, spec: Spec, window: float = WINDOW, now: float | None = None) -> list[Problem]:
    now = now or time.time()
    since = now - window
    ev, ms = project.events, project.measurements
    out: list[Problem] = []

    def say(code, msg, where, about):
        out.append(Problem("finding", msg, where, code, about))

    # a stock heading for its limit
    for st in spec.stocks.values():
        if st.limit is None:
            continue
        pts = sorted(p for s in st.sensors.values() for p in ms.range(s.series, since, now))
        k = slope(pts)
        if k is None or k <= 0 or not pts:
            continue
        left = (st.limit - pts[-1][1]) / k
        if 0 < left < HORIZON:
            guarded = [g for g in spec.goals.values() if g.of.kind == "stock" and g.of.name == st.name]
            say("heading-for-limit", f"stock {st.name}: growing {k * 3600:.3g} {st.unit or ''}/h; at this rate it reaches "
                f"its limit ({st.limit:g}) in {human(left)}" + ("" if guarded else ", and no goal guards it"), st.where,
                f"stock.{st.name}")
    # a block saturating: moved less than commanded
    for b in spec.blocks.values():
        if not b.machine:
            continue
        runs = [e for e in ev.query(n=200, type="agent.ran", item=b.name, since=since) if "commanded" in e["data"]]
        short = [e for e in runs if sum((e["data"].get("moved") or {}).values()) < e["data"]["commanded"] * 0.999]
        clamped = [e for e in ev.query(n=200, type="block.commanded", item=b.name, since=since) if "asked" in e["data"]]
        if len(runs) >= 3 and len(short) / len(runs) > 0.5 and any(t.kind == "flow" for t in b.targets()):
            say("saturating", f"block {b.name}: moved less than it was commanded in {len(short)} of {len(runs)} runs: at "
                f"its limit, or the work is not there", b.where, f"block.{b.name}")
        if len(clamped) >= 3:
            say("clamped", f"block {b.name}: {len(clamped)} commands were more than its max ({b.max:g}) allows", b.where,
                f"block.{b.name}")
        failed = ev.query(n=50, type="agent.failed", item=b.name, since=since)
        if len(failed) >= 3:
            say("failing", f"block {b.name}: failed {len(failed)} times ({failed[-1]['data'].get('note', '')})", b.where,
                f"block.{b.name}")
    # a block whose claims the record contradicts (SPEC §12g)
    bad: dict[str, list[dict]] = {}
    for e in ev.query(n=500, type="ergostat.claim.contradicted", since=since):
        bad.setdefault(e["data"].get("block") or "", []).append(e)
    for name, es in bad.items():
        b = spec.blocks.get(name)
        made = ev.query(n=1, item=es[-1]["item"], type="ergostat.claim.made")
        says = made[-1]["data"].get("says", "") if made else ""
        say("contradicted-claim", f"block {name}: {len(es)} claim{'s' if len(es) > 1 else ''} contradicted in the last "
            f"{human(window)} (latest: {says!r}: {es[-1]['data'].get('why', '')}; {es[-1]['item']})",
            b.where if b else None, f"block.{name}")
    # a person asked and not answering
    for e in ev.query(n=100, type="person.asked", since=since):
        b = spec.blocks.get(e.get("item") or "")
        if b is None:
            continue
        answered = ev.query(n=1, type="agent.ran", item=b.name, since=e["time"])
        if not answered and now - e["time"] > PERSON_WAIT:
            say("not-answering", f"block {b.name}: asked {human(now - e['time'])} ago ({b.params.get('ask', '')}), no answer; "
                f"they report with ergostat block {b.name} --done N", b.where, f"block.{b.name}")
    # a sensor gone quiet
    for s in spec.sensors():
        if s.manual or not s.measured:
            continue
        last = ms.latest(s.series)
        period = s.every or 60.0
        if last is None:
            fails = ev.query(n=1, type="sensor.failed", item=f"{s.of.name}.{s.name}", since=since)
            if fails:
                say("sensor-failing", f"sensor {s.of.name}.{s.name}: no reading yet: {fails[-1]['data'].get('why', '')}",
                    s.where, f"{s.of.kind}.{s.of.name}.{s.name}")
        elif now - last[0] > 3 * period and project_running(project):
            say("sensor-stale", f"sensor {s.of.name}.{s.name}: last read {human(now - last[0])} ago (every {human(period)})",
                s.where, f"{s.of.kind}.{s.of.name}.{s.name}")
    # goals off, and critical goals decaying
    for g in spec.goals.values():
        lp = spec.loop(g.name)
        last = ev.query(n=1, type="loop.*", item=g.name)
        if last and last[-1]["type"] == "loop.off" and now - last[-1]["time"] > 600:
            moved = [e for a in lp.actuators for e in ev.query(n=1, type="valve.opened", source=a, since=last[-1]["time"])]
            if lp.actuators and not moved:
                say("not-answered", f"goal {g.name}: off for {human(now - last[-1]['time'])}, and "
                    f"{', '.join(lp.actuators)} moved nothing since", g.where, f"goal.{g.name}")
        if not g.critical:
            continue
        if not g.owner:
            say("critical-unowned", f"goal {g.name} is critical and has no owner: nobody answers for it", g.where,
                f"goal.{g.name}")
        recent = recoveries(ev.query(n=None, type="loop.*", item=g.name, since=since))
        before = recoveries(ev.query(n=None, type="loop.*", item=g.name, since=since - 4 * window, until=since))
        if len(recent) >= 2 and len(before) >= 2:
            a, b = sum(recent) / len(recent), sum(before) / len(before)
            if a > 1.5 * b and a - b > 60:
                say("critical-decaying", f"goal {g.name} (critical): recovers in {human(a)} on average now, against "
                    f"{human(b)} before: its loop is answering more slowly", g.where, f"goal.{g.name}")
    repeated(project, say)
    exercised(project, spec, now, say)
    return out


def exercised(project, spec: Spec, now: float, say) -> None:
    """The parts the record has not exercised (``numbers/exercised.py``), on the reference window the estimates read:
    a finding on each, with its span of record and why, cleared the moment the part moves."""
    from ..numbers import exercised as ex
    try:
        _, q = ex.of_project(project, spec, now)
    except Exception:                                  # a record that cannot be read says nothing here
        return
    for ref, x in sorted(q.items()):
        kind, _, name = ref.partition(".")
        part = spec.measured(kind).get(name)
        say(ex.CODE, ex.said(x), getattr(part, "where", None), ref)


def repeated(project, say) -> None:
    """A correction the owner gave again: the first did not change what was done. Raised while the latest repeat
    waits for the owner (proposed), or the correction it repeats is in force (confirmed)."""
    from ..decisions import acts
    from ..decisions.kinds import CORRECTION
    its = {i.id: i for i in acts.items(project, CORRECTION)}
    by: dict[str, list] = {}
    for i in its.values():
        r = i.fields.get("repeats")
        if r in its and i.state != "dismissed":
            by.setdefault(r, []).append(i)
    for first, reps in by.items():
        f = its[first]
        if f.state in ("dismissed", "retired") or not (f.state == "confirmed" or any(r.state == "proposed" for r in reps)):
            continue
        last = max(reps, key=lambda r: r.first)
        say("correction-repeated", f"correction {first}: given {len(reps) + 1} times (last {human(time.time() - last.first)} "
            f"ago, {last.id}): {f.fields.get('correction', '')}", None, first)


def project_running(project) -> bool:
    from .. import runner
    try:
        return bool(runner.running_pid(project, wait=False))
    except Exception:
        return False
