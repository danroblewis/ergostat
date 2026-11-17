"""A step test, run by ``ergostat run`` only once the owner has approved it (SPEC §12c): the loop's
controller is held still, the setting's value is recorded, the block that moves u is run once with
``"trigger": "step-test"`` and a command of exactly the step, the loop is left to answer for the
hold, then the same block puts the setting back to the value it had (``"to"``), not back by the
step (a step a limit cut short would otherwise leave it elsewhere), and the loop answers again;
then the controller takes over. Before it starts, the step must fit within the setting's limits;
after each move, the block must say it moved what it was commanded (to within the setting's
resolution), else the test puts the setting back and stops (Seborg et al. §7). Each move is recorded
(``steptest.started``, ``steptest.stepped``, ``steptest.finished``), so the identification can read
the test as an open-loop experiment: the step up fitted, the step back held out.

The test stops early, stepping back at once, when the goal's error goes past the plan's ``abort``
(it moved more than the plan allowed), and when ergostat stops; an approval older than
``STALE`` when ergostat starts is not run (it was approved for a system as it was then)."""

from __future__ import annotations

import threading
import time

SOURCE = "ergostat"
STALE = 600.0
POLL = 1.0


def _open(p) -> list[dict]:
    """Approvals with no start, and starts with no finish, newest first."""
    approved = p.events.query(n=50, type="steptest.approved")
    done = {e["data"].get("test") for e in p.events.query(n=200, type="steptest.started,steptest.finished")}
    return [e for e in reversed(approved) if e["data"].get("id") not in done]


def resume(eng) -> None:
    """At start: a test cut off by a stop is said finished; one approved a moment ago is run."""
    p = eng.p
    started = {e["data"].get("test"): e for e in p.events.query(n=200, type="steptest.started")}
    finished = {e["data"].get("test") for e in p.events.query(n=200, type="steptest.finished")}
    for tid, e in started.items():
        if tid not in finished:
            p.events.add("steptest.finished", item=e["item"], source=SOURCE,
                         data={"test": tid, "how": "cut off: ergostat stopped during it, and its controller took over"})
    for e in _open(p):
        if time.time() - e["time"] > STALE:
            p.events.add("steptest.finished", item=e["item"], source=SOURCE,
                         data={"test": e["data"].get("id"), "how": "not run: approved while ergostat was not running"})
        else:
            begin(eng, e)


def begin(eng, approval: dict) -> None:
    plan = approval["data"]
    if plan.get("block") not in eng.spec.blocks or plan.get("goal") not in eng.spec.goals:
        eng.p.events.add("steptest.finished", item=approval.get("item"), source=SOURCE,
                         data={"test": plan.get("id"), "how": "not run: its block or goal is no longer in the model"})
        return
    threading.Thread(target=run, args=(eng, plan), name=f"ergostat-step-test-{plan.get('id')}", daemon=True).start()


def _step(eng, b, plan: dict, amount: float, to: float | None = None) -> float | None:
    """Run the block once, commanded to move exactly ``amount`` (or to put the setting at ``to``);
    what it said it moved of the plan's flow, None when it said nothing."""
    with eng.lock:
        eng.running.add(b.name)
        eng.began[b.name] = time.time()
    eng.testing[b.name] = {"amount": amount, "id": plan["id"], **({"to": to} if to is not None else {})}
    moved: list[str] = []
    getattr(eng, "moved_by", {}).pop(b.name, None)
    try:
        moved = eng.run_block(b, "step-test")
    finally:
        eng.testing.pop(b.name, None)
        with eng.lock:
            for s in eng.after_acting(moved):
                eng.read_soon(s)
            eng.running.discard(b.name)
            eng.finished[b.name] = time.time()
    said = getattr(eng, "moved_by", {}).get(b.name)
    if said is None:
        return None
    flow = plan.get("flow")
    return float(said.get(flow, 0.0)) if flow else float(sum(said.values()))


def _wait(eng, plan: dict, seconds: float) -> str | None:
    """Wait while the loop answers; why it stopped early, if it did."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if eng.stop.wait(POLL):
            return "ergostat stopped"
        e = eng.signals.get(f"goal.{plan['goal']}.error")
        if e is not None and plan.get("abort") is not None and abs(e) > plan["abort"]:
            return f"the error reached {abs(e):.3g}, past the {plan['abort']:.3g} the plan allowed"
    return None


def _close(moved: float | None, want: float, res: float | None) -> bool:
    return moved is not None and abs(moved - want) <= max((res or 0.0) / 2, 1e-6 * abs(want)) + 1e-9


def _fits(u0: float, amount: float, limits) -> bool:
    lo, hi = (limits or [None, None])[:2]
    v = u0 + amount
    return (lo is None or v >= lo - 1e-9) and (hi is None or v <= hi + 1e-9)


def run(eng, plan: dict) -> None:
    p = eng.p
    tid, goal = plan["id"], plan["goal"]
    b = eng.spec.blocks[plan["block"]]
    hold = [x for x in plan.get("hold_blocks", [b.name]) if x in eng.spec.blocks]
    res = plan.get("resolution")
    amount = plan["amount"]
    eng.held.update(hold)
    how = "done"
    u0 = None
    try:
        deadline = time.monotonic() + 120
        while any(x in eng.running for x in hold) and time.monotonic() < deadline and not eng.stop.is_set():
            time.sleep(0.2)                                     # a run already under way finishes first
        u0 = eng.signals.get(plan["u"]) if plan.get("u") else None
        p.events.add("steptest.started", item=goal, source=SOURCE, data={"test": tid, "block": b.name, "held": hold,
                                                                          "amount": amount, "hold": plan["hold"], "from": u0})
        if plan.get("u") and u0 is None:
            how = f"not run: {plan['u']} has no reading to put it back to"
            return
        if u0 is not None and not _fits(u0, amount, plan.get("limits")):
            lo, hi = plan["limits"]
            how = f"not run: {u0:g} {'+' if amount > 0 else '−'} {abs(amount):g} is outside {lo:g} to {hi:g}"
            return
        moved = _step(eng, b, plan, amount)
        p.events.add("steptest.stepped", item=goal, source=SOURCE,
                     data={"test": tid, "amount": amount, "moved": moved, "phase": "up"})
        why = None
        if not _close(moved, amount, res):
            why = (f"{b.name} said it moved {moved:g}, not the {amount:g} commanded" if moved is not None
                   else f"{b.name} did not say what it moved")
        if why is None:
            why = _wait(eng, plan, plan["hold"])
        back = -(moved if moved is not None else amount)
        moved_back = _step(eng, b, plan, back, to=u0)
        p.events.add("steptest.stepped", item=goal, source=SOURCE,
                     data={"test": tid, "amount": back, "moved": moved_back, "to": u0, "phase": "back"})
        if why is None and not _close(moved_back, back, res):
            why = (f"{b.name} said it moved {moved_back:g} putting it back, not the {back:g} to {u0:g}"
                   if moved_back is not None else f"{b.name} did not say what it moved putting it back")
        if why is None:
            why = _wait(eng, plan, plan["hold"])
        if why:
            how = f"stopped early: {why}"
    except Exception as e:                                    # the controller must get its loop back whatever happened
        how = f"stopped: {type(e).__name__}: {e}"
    finally:
        eng.held.difference_update(hold)
        p.events.add("steptest.finished", item=goal, source=SOURCE, data={"test": tid, "how": how, "from": u0})
        eng.say(f"step test {tid} on {goal}: {how}")
