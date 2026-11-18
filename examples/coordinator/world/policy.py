"""The Coordinator's control laws, two ways: the harness as it was, and the architecture designed in
docs/proposals/coordinator/07 to 10. Each loop is one function of the plant (world/plant.py), run by its block in
ergostat (bin/coord.py LOOP) or by the experiment (world/experiment.py) on the same clock. Each reads only what a
real deployment could read (the items' states, the runs' last events, the owner's presence, the record's counts),
never a defect hidden in the work, and acts only through the plant's actuators.

`harness` is the long session's implicit policy, as the record shows it (02, 03): fan-out grows with the work
waiting; tests are read through a pipe unless a recent incident restored the habit (RM5's discipline, which
erodes); a stalled agent is noticed when the Coordinator happens to look, which it does often while the owner is
there and seldom with several agents running and the owner away (RM6); every proposal is admitted (R5); every
question waits for the owner (RM8); a correction is written down now and then, else held in the window until the
next cut (B9), and nothing written is ever retired (RM4b, RM15).

`designed` is LP1 to LP10 with their *proposed* defaults (07), the operating states of 08 (owner present or
away; normal or consolidation) and H1, the permissive that reads every test's exit status.

Each function returns what it moved, by flow name: the numbers its block reports to ergostat.
"""

from __future__ import annotations

import math

from world.plant import CATCH, DEPTHS, Plant

CAP = 6                                   # the owner's cap on the AI-agent pool: the owner's one lever on throughput

# -- defaults of the design (07; all *proposed*, configurable) -------------------------------------------------
TTL = 40 / 60                             # LP5: the AI-agent tier's lease, 40 minutes
ATTEMPTS = 3                              # LP5: counted attempts before the dead-letter stock
REDRIVE_AFTER = 4.0                       # LP5: the dead-letter diagnoser redrives with hints within hours
H_STAR = 0.10                             # LP1's setpoint to start: the hidden rework allowed per item
H_BAND = (0.02, 0.30)                     # LP2's clamp on h*
CV1_LIMIT, DEADBAND, KI = 0.10, 0.02, 1 / 8   # LP2: escaped rework ≤ 0.1, zone ±0.02, Ki an eighth a day
S5 = 3                                    # LP7: blockers open at most
S1 = 4                                    # LP7: interruptions a day
B0, BG = 0.3, 0.2                         # LP6: the admission bar b = b0 + g · waiting / capacity
ENTER, LEAVE, DWELL = 1.3, 1.1, 7 * 24    # LP10: consolidation's hysteresis and dwell
RETIRE_AFTER = 48.0                       # LP9: a correction absorbed into a check that held this long is retired

# The observer's prior for x̂4 (06 §2): the quality fraction against direction age, as L5 identified it from the
# record (not the plant's own numbers: identification is never exact).
PRIOR = (0.45, 0.05, 14.0)


def present(p: Plant) -> bool:
    return p.present()


def ctrl(p: Plant) -> dict:
    return p.s["ctrl"]


def due(p: Plant, loop: str, period: float) -> bool:
    """Run this loop's law if its period has passed (a loop sampled on a clock)."""
    c = ctrl(p).setdefault("last", {})
    if p.t - c.get(loop, -1e9) < period - 1e-9:
        return False
    c[loop] = p.t
    return True


# ===== the harness, as it was ===================================================================================

def h_dispatch(p: Plant) -> dict:
    """Fan-out by pressure (B2): more agents the more is waiting, up to the cap, owner or not; first come first
    served."""
    ready = p.ids("ready")
    ready = [i for i in ready if not p.item(i).get("waiting_owner")]
    want = min(CAP, 1 + len(ready) // 12)
    n = 0
    brief = 1 + 0.06 * p.running()                       # R10: the more at once, the thinner each brief
    for i in ready:
        if p.running() >= want:
            break
        p.lease(i, brief=brief, brief_tokens=960)
        n += 1
    return {"leased": n}


def h_acceptance(p: Plant) -> dict:
    """The tests are run and read through a pipe, unless an incident lately restored the habit of reading the
    exit status (B4's discipline, eroding: RM5). Questions about intent wait for the owner."""
    c = ctrl(p)
    d = c.setdefault("discipline", 0.0)
    last = c.get("disc_t", p.t)
    tau = 30.0 if p.present() else (15.0 if p.running() >= 2 else 30.0)
    d *= math.exp(-(p.t - last) / tau)
    seen = c.setdefault("incidents_seen", 0)
    for k in range(seen, len(p.s["incidents"])):          # a red mainline after a hidden run: the slip reported?
        if d < 0.5 and p.u("incident-reported", k) < 0.6:
            d = 1.0
            p.count("incidents")
    c["incidents_seen"] = len(p.s["incidents"])
    c["discipline"], c["disc_t"] = d, p.t
    out = {"accepted": 0, "rejected": 0, "asked": 0}
    for i in p.ids("reported"):
        it = p.item(i)
        if it.get("waiting_owner"):
            continue
        if "check" not in it:
            if not it.get("asked") and p.u("question", i, it["attempts"]) < question_rate(p, it):
                it["asked"] = True
                p.ask_owner(i, "intent", interrupt=True)
                out["asked"] += 1
                continue
            p.start_check(i, "tests", read_status=p.u("read", i, it["attempts"]) < d)
        if p.check_due(i):
            if p.inspect(i):
                p.reject(i)
                out["rejected"] += 1
            else:
                p.accept(i)
                out["accepted"] += 1
                propose_after(p, i)
    return out


def h_watch(p: Plant) -> dict:
    """No lease: a silent agent is noticed when the Coordinator looks at it. It looks often with the owner there
    (the owner's questions make it look), seldom with the owner away and several agents to watch (R3, RM6)."""
    n = 0
    dt = p.t - ctrl(p).get("watch_t", p.t)
    ctrl(p)["watch_t"] = p.t
    running = p.running()
    rate = 2.5 if p.present() else 0.9 / max(1.0, running / 2)
    for r, run in list(p.s["runs"].items()):
        if run["stall_at"] is not None and p.t >= run["stall_at"] and p.chance(rate, dt, "notice", r, round(p.t * 30)):
            p.expire(r, "noticed")                             # salvaged: what it left is committed, the rest redone
            n += 1
    return {"expired": n, "dead-lettered": 0, "redriven": 0}


def h_admission(p: Plant) -> dict:
    """Every idea becomes work (R5): nothing at the door."""
    n = 0
    for i in p.ids("proposed"):
        p.admit(i)
        n += 1
    return {"admitted": n, "declined": 0}


def h_attention(p: Plant) -> dict:
    """No budget: every question interrupts, and the proposed decisions wait for a confirmation that never comes
    (RM8)."""
    return {"asked": 0}


def h_externalise(p: Plant) -> dict:
    """A correction is written down now and then, when the owner asks for it; otherwise it lives in the window
    until the next cut. Nothing written is retired (RM4b, RM15)."""
    n = 0
    for k, c in p.s["corr"].items():
        if c["state"] == "window" and p.t - c["t"] > 2.0 and not c.get("looked"):
            c["looked"] = True
            if p.u("written", k) < 0.25:
                p.externalise(k)
                n += 1
    return {"externalised": n, "retired": 0}


def h_quality(p: Plant) -> dict:
    return {"allowance": 0.0}


def h_consolidation(p: Plant) -> dict:
    return {"mode": 0.0}


# ===== the designed Coordinator =================================================================================

def wip_limit(p: Plant) -> int:
    """S2, scheduled on the owner's presence (d2): the cap present, half of it for AI agents away (07 §2)."""
    if ctrl(p).get("mode") == "incident":
        return 0
    return CAP if p.present() else CAP // 2


def priority(p: Plant, i: str) -> tuple:
    """LP6's order: rework of landed work first (it holds others' work up), then the owner's directions, then
    the rest by cost of delay over size, with an ageing term so nothing starves."""
    it = p.item(i)
    cls = 0 if it.get("reworked") else (1 if it["origin"] == "direction" else 2)
    wsjf = it["value"] / max(it["lines"], 1) * 100 + 0.02 * (p.t - it["since"])
    return (cls, -wsjf, int(i.split("/")[1]))


def d_dispatch(p: Plant) -> dict:
    """LP3: a WIP-capped pull (CONWIP) of the ordered queue whenever a slot is free; lowering the limit drains, it
    kills nothing. The brief is the master recipe rendered (u2): the owner's words, decisions and corrections whole."""
    ready = sorted(p.ids("ready"), key=lambda i: priority(p, i))
    limit = wip_limit(p)
    n = 0
    for i in ready:
        if p.running() >= limit:
            break
        p.lease(i, brief=0.85, brief_tokens=4000)
        n += 1
    return {"leased": n}


def x4(p: Plant, it: dict) -> float:
    """The observer's estimate of the hidden rework in an item if it is accepted unchecked (x̂4, 06 §2): the prior
    against direction age, lowered by the learning in force."""
    peak, floor, tau = PRIOR
    age = p.age_of_direction(it)
    return (floor + (peak - floor) * math.exp(-age / tau)) * 0.85 / (1 + 0.12 * p.rules_for(it["dir"]))


def escapes(x: float, depth: str) -> float:
    cf, cs = CATCH[depth]
    return x * (0.25 * (1 - cf) + 0.75 * (1 - cs))


def d_acceptance(p: Plant) -> dict:
    """LP1, the inner loop of the quality cascade: the least depth whose expected escapes fall under h*, one level
    deeper with the owner away, never below the tests with their exit status read (H1). A hold point needs room
    under S5; without it, deep review by an AI agent (the override, 07 §2)."""
    h = ctrl(p).setdefault("h_star", H_STAR)
    away = not p.present()
    out = {"accepted": 0, "rejected": 0, "asked": 0}
    for i in p.ids("reported"):
        it = p.item(i)
        if it.get("waiting_owner"):
            continue
        if "check" not in it:
            if not it.get("asked") and p.u("question", i, it["attempts"]) < question_rate(p, it):
                it["asked"] = True                          # u7: ask only where a wrong act cannot be undone
                if p.u("irreversible", i) < 0.25 and room(p):
                    p.ask_owner(i, "intent", interrupt=spend_token(p))
                    out["asked"] += 1
                    continue
                p.count("assumed")                          # proceed, the assumption marked uncertain in the report
            x = x4(p, it)
            depth = next((d for d in DEPTHS[2:] if escapes(x, d) <= h), "hold-point")
            if away and depth != "hold-point":
                depth = DEPTHS[DEPTHS.index(depth) + 1]
            if depth == "hold-point" and not room(p):
                depth = "deep-review"
                p.count("override")
            p.count(f"depth-{depth}")
            p.start_check(i, depth, read_status=True)
            if depth == "hold-point":
                p.ask_owner(i, "hold point", interrupt=spend_token(p))
                out["asked"] += 1
        if p.check_due(i):
            if p.inspect(i):
                p.reject(i)
                out["rejected"] += 1
            else:
                p.accept(i)
                out["accepted"] += 1
                propose_after(p, i)
    return out


def room(p: Plant) -> bool:
    return len(p.s["owner"]["queue"]) < S5


def spend_token(p: Plant) -> bool:
    """S1's token bucket: an interruption now if a token is left (and, away, only for the top priority);
    otherwise the ask waits, batched, for the handover report."""
    c = ctrl(p)
    tok = c.get("tokens", float(S1))
    tok = min(float(S1), tok + (p.t - c.get("tok_t", p.t)) * S1 / 24)
    c["tok_t"] = p.t
    if p.present() and tok >= 1:
        c["tokens"] = tok - 1
        return True
    c["tokens"] = tok
    p.count("batched")
    return False


def d_watchdog(p: Plant) -> dict:
    """LP5, on the program tier and outside the workers: a run silent past its tier's lease is expired and its
    item requeued; after three counted attempts it goes to the dead-letter stock, whose diagnoser redrives it
    with hints."""
    out = {"expired": 0, "dead-lettered": 0, "redriven": 0}
    for r, run in list(p.s["runs"].items()):
        if p.silence(r) > TTL:
            if p.item(run["item"])["attempts"] >= ATTEMPTS:
                p.dead_letter(r)
                out["dead-lettered"] += 1
            else:
                p.expire(r, "lease expired")
                out["expired"] += 1
    for i in p.ids("dead-letter"):
        if p.t - p.item(i)["since"] >= REDRIVE_AFTER:
            p.redrive(i)
            out["redriven"] += 1
    return out


def d_admission(p: Plant) -> dict:
    """LP6 at the door: an estimate of each proposal's value (noisy, as a narrow AI's is) against a bar that rises
    as the standard work waiting outgrows the pool's capacity. In consolidation only fixes and removals pass."""
    out = {"admitted": 0, "declined": 0}
    waiting = sum(1 for i in p.ids("ready") if p.item(i)["origin"] != "direction")
    bar = B0 + BG * waiting / (CAP * 4)
    consolidating = ctrl(p).get("mode") == "consolidation"
    for i in p.ids("proposed"):
        it = p.item(i)
        if it["origin"] == "removal":
            p.admit(i)
            out["admitted"] += 1
            continue
        v = it["value"] + 0.15 * (p.u("estimate", i) - 0.5) * 2
        if (consolidating and v < 0.85) or v < bar:
            p.decline(i, "below the bar" if not consolidating else "consolidating")
            out["declined"] += 1
        else:
            p.admit(i)
            out["admitted"] += 1
    return out


def d_attention(p: Plant) -> dict:
    """LP7's other half: on the owner's return (an event, not a clock) the handover report, in which the owner
    answers what was batched and confirms the decisions proposed meanwhile."""
    o = p.s["owner"]
    c = ctrl(p)
    if p.present() and o.get("returned") is not None and c.get("report_for") != o["returned"]:
        c["report_for"] = o["returned"]
        o["report_read"] = True
        took = min(o["decisions"], 20.0)
        o["decisions"] -= took
        p.count("decisions-confirmed", took)
        p.emit("report.read", "report/handover", decisions=round(took, 2))
        return {"handover": 1}
    if not p.present():
        o["report_read"] = False
    return {"handover": 0}


def d_externalise(p: Plant) -> dict:
    """LP9: every correction recorded within the hour of being said, used in briefs at once (marked uncertain);
    one compiled into a check that has held is retired by ergostat itself (06 §4.4)."""
    out = {"externalised": 0, "retired": 0}
    for k, c in p.s["corr"].items():
        if c["state"] == "window" and p.t - c["t"] >= 0.5:
            p.externalise(k)
            out["externalised"] += 1
        elif c["state"] == "rule" and c["checkable"] and p.t - c["written"] >= RETIRE_AFTER:
            p.retire(k, "absorbed into a check that held")
            out["retired"] += 1
    return out


def d_quality(p: Plant) -> dict:
    """LP2, the outer loop: once a day, integral action on escaped rework (CV1, a week's window) moves LP1's
    setpoint h* within its band, with a deadband, and no integration while LP1 is saturated or the window holds
    fewer than ten acceptances (conditional integration)."""
    c = ctrl(p)
    h = c.setdefault("h_star", H_STAR)
    cv1, n = p.escaped_share(7)
    e = cv1 - CV1_LIMIT
    m = p.s["m"]
    since = int(p.t) - 24
    deep = sum(v.get("depth-hold-point", 0) + v.get("override", 0) for k, v in m.items() if int(k) >= since)
    total = sum(sum(x for kk, x in v.items() if kk.startswith("depth-")) for k, v in m.items() if int(k) >= since)
    saturated = total and deep / total > 0.8
    step = 0.0
    if n >= 10 and abs(e) > DEADBAND and not saturated:
        step = -KI * e
        h2 = min(H_BAND[1], max(H_BAND[0], h + step))
        step, c["h_star"] = h2 - h, h2
    p.log("h_star", [p.t, c["h_star"], cv1])
    return {"allowance": step}


def d_consolidation(p: Plant) -> dict:
    """LP10: code per feature against its expected cost, daily; consolidation entered at 1.3 and left at 1.1, a
    week's dwell in each. (The switch is decided through review in the design: here the review always agrees.)
    In consolidation, removals are briefed: a few a day."""
    c = ctrl(p)
    mode = c.get("mode", "normal")
    since = c.get("mode_t", -1e9)
    r = p.cv8()
    moved = 0.0
    if mode == "normal" and r >= ENTER and p.t - since >= DWELL:
        c["mode"], c["mode_t"], moved = "consolidation", p.t, 1.0
        p.emit("mode.changed", "mode/factory", mode="consolidation", ratio=round(r, 3))
    elif mode == "consolidation" and r <= LEAVE and p.t - since >= DWELL:
        c["mode"], c["mode_t"], moved = "normal", p.t, -1.0
        p.emit("mode.changed", "mode/factory", mode="normal", ratio=round(r, 3))
    if c.get("mode") == "consolidation":
        for _ in range(6):
            p.add_removal()
        p.s["code"]["inflation"] *= 0.6                    # the recipes revised: the workers stop inflating
    return {"mode": moved}


# ===== shared ===================================================================================================

def question_rate(p: Plant, it: dict) -> float:
    """Questions about intent: many while a direction is new, few later (RM8: 17% of turns ended in one)."""
    return 0.03 + 0.15 * math.exp(-p.age_of_direction(it) / 24)


def propose_after(p: Plant, i: str) -> None:
    """Work done suggests more (R5): a page, a test, a document, a further proposal. In consolidation the
    workers' recipes are revised so they stop inflating it."""
    rate = 0.5 if ctrl(p).get("mode") != "consolidation" else 0.15
    if p.item(i)["origin"] != "removal" and p.u("proposes", i, p.item(i)["attempts"]) < rate:
        p.propose()


LOOPS = {
    # loop: (period in factory hours for the experiment, harness law, designed law)
    "dispatch": (1 / 30, h_dispatch, d_dispatch),
    "acceptance": (1 / 30, h_acceptance, d_acceptance),
    "watchdog": (1 / 30, h_watch, d_watchdog),
    "admission": (1 / 30, h_admission, d_admission),
    "attention": (1 / 30, h_attention, d_attention),
    "externalise": (1 / 6, h_externalise, d_externalise),
    "quality": (24.0, h_quality, d_quality),
    "consolidation": (24.0, h_consolidation, d_consolidation),
}


def law(policy: str, loop: str):
    return LOOPS[loop][1 if policy == "harness" else 2]
