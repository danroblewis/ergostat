"""The relative gain array of a system's loops (Bristol 1966; Skogestad & Postlethwaite §3.4, §10.6), from the step
tests the owner approved (``steptest``), said by ``explain system.NAME``.

Each test gives one row: for every loop of the system, how far its u and its y moved, as held over the last quarter of
the hold (the mean over ``[back − hold/4, back)`` less the mean over the quarter before the step). With the other
controllers acting, their u moves too, and the rows are fitted together (ΔY = ΔU Gᵀ, least squares), so G is the
open-loop steady-state gain matrix as far as each step had settled. Λ = G ⊙ (G⁻¹)ᵀ, on the pairing as built: each
loop's own u. A test is used only if it was made of the system as it is now: its stamp (at its start and at its
finish) of every system enclosing the stepped goal must match ``plant_signature(spec, NAME)`` now, string for string."""

from __future__ import annotations

import math
import time

from ..numbers.estimate import _invert
from ..numbers.redesign_due import signature
from ..spec.architecture import _chains
from . import record
from .loop import tests_in

MOST_LOOPS = 8             # a system of more loops is not worked out (a matrix this size from step tests is not credible)
MOST_TESTS = 12            # the latest tests in record order, for the whole system
COND = 100.0               # sqrt of the 1-norm condition number of ΔUᵀΔU (columns scaled by their RMS) past which: not computed
FIGHT = 10.0               # a relative gain past this: the loops fight
# The after window's two halves may differ by this share of Δ (plus twice the noise before). A ramp (an integrator not
# declared) always differs by 1/7 of Δ, whatever its slope; a first-order lag of time constant τ by 0.016 at τ = hold/4,
# 0.030 at hold/3 (93% of its gain held), 0.053 at hold/2. So a ramp, or a lag far from settled, is left out.
SETTLE = 0.03
KINDS = ("stock", "flow", "auxiliary")


def _goals(spec, system: str) -> list[str]:
    return sorted(r.split(".", 1)[1] for r, ch in _chains(spec).items() if r.startswith("goal.") and system in ch)


def plant_signature(spec, system: str) -> str:
    """The system's process as written: its stocks, flows and auxiliaries and the parameters their equations use, and
    which u each of its loops moves (a controller rewired to another actuator is another experiment). Goals and blocks
    are otherwise left out, so accepting a ``process:`` or a controller's ``gain:`` keeps the tests."""
    from ..numbers import version as ver
    us = [[g, s.u if (s := record.signals(spec, g)) is not None else None] for g in _goals(spec, system)]
    return ver._hash([signature(spec, system, kinds=KINDS), us])


def no(why: str) -> dict:
    return {"computed": False, "why": why}


def _unusable(t: dict, name: str, now_sig: str) -> str | None:
    """Why a test does not count for system ``name``, or None."""
    if not str(t.get("how") or "").startswith("done"):
        return f"it did not finish done ({t.get('how') or 'never finished'})"
    if any(t.get(k) is None for k in ("up", "back", "finished")):
        return "it has no step up, step back or finish recorded"
    for k, when in (("plant", "start"), ("plant_after", "finish")):
        stamp = t.get(k)
        if not isinstance(stamp, dict) or not isinstance(stamp.get(name), str):
            return f"it carries no stamp of system {name} at its {when}"
        if stamp[name] != now_sig:
            return f"system {name} has changed since its {when}"
    return None


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _sd(xs: list[float]) -> float:
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0


def _moves(p, sigs: dict, t: dict) -> tuple[list[float], list[float]] | str:
    """One test's (Δu, Δy) for every loop, or why it is left out."""
    up, back = float(t["up"]), float(t["back"])
    w = float(t.get("hold") or (back - up)) / 4
    du, dy = [], []
    for sig in sigs.values():
        # each window read on its own, ending just before its end: a reading at the step itself is never in it
        spans = [record.read(p, sig, *record.fine(p, sig, a, b - 1e-6))
                 for a, b in ((up - w, up), (back - w, back - w / 2), (back - w / 2, back))]
        for var, ref, out in (("u", sig.u, du), ("y", sig.y, dy)):
            before, first, last = ([v for v in d[var] if v is not None] for d in spans)
            if not before or not first or not last:
                return f"no reading of {ref}"
            delta = _mean(first + last) - _mean(before)
            if abs(_mean(last) - _mean(first)) > SETTLE * abs(delta) + 2 * _sd(before):
                return f"not settled: {ref} still moving at the end of its hold"
            out.append(delta)
    return du, dy


def _norm1(a: list[list[float]]) -> float:
    return max(sum(abs(r[j]) for r in a) for j in range(len(a[0])))


def solve(du: list[list[float]], dy: list[list[float]], goals: list[str]) -> dict:
    """The gains and their relative gain array from moves (tests × loops), or why not."""
    m = len(goals)
    scale = [math.sqrt(sum(r[j] ** 2 for r in du) / len(du)) if du else 0.0 for j in range(m)]
    if not all(scale):
        return no("the moves were collinear (a loop's u never moved)")
    us = [[r[j] / scale[j] for j in range(m)] for r in du]
    a = [[sum(r[i] * r[j] for r in us) for j in range(m)] for i in range(m)]
    ai = _invert(a)
    if ai is None:
        return no("the moves were collinear")
    cond = math.sqrt(_norm1(a) * _norm1(ai))
    if cond > COND:
        return no(f"the moves were nearly collinear (condition number about {cond:.3g}, past {COND:g})")
    uty = [[sum(r[j] * y[k] for r, y in zip(us, dy, strict=True)) for k in range(m)] for j in range(m)]
    gt = [[sum(ai[j][i] * uty[i][k] for i in range(m)) / scale[j] for k in range(m)] for j in range(m)]
    g = [[gt[j][i] for j in range(m)] for i in range(m)]               # g[i][j]: from u_j to y_i
    gi = _invert(g)
    if gi is None:
        return no("the gains found are singular")
    lam = [[g[i][j] * gi[j][i] for j in range(m)] for i in range(m)]
    notes = [f"never pair on a negative relative gain: {goals[i]}" for i in range(m) if lam[i][i] < 0]
    notes += [f"the loops fight: {goals[i]}" for i in range(m) if lam[i][i] > FIGHT]
    if m == 2 and abs(lam[0][1] - 1) < abs(lam[0][0] - 1):
        notes.append(f"swapped, λ {lam[0][1]:.2f}: pair {goals[0]} with {goals[1]}'s u instead")
    return {"computed": True, "goals": goals, "G": g, "lambda": lam, "notes": notes, "tests": len(du)}


def of(p, spec, name: str, now: float | None = None) -> dict | None:
    """System ``name``'s relative gain array from its approved step tests, or why not; None when it has fewer than two
    loops."""
    now = now if now is not None else time.time()
    sigs = {g: s for g in _goals(spec, name) if (s := record.signals(spec, g)) is not None and s.u}
    if len(sigs) < 2:
        return None
    if len(sigs) > MOST_LOOPS:
        return no(f"{len(sigs)} loops, more than the {MOST_LOOPS} it is worked out for")
    for g, s in sigs.items():
        pr = spec.goals[g].process
        if (pr and pr.get("form") == "integrating") or s.known is not None:
            return no(f"{g} is an integrator, and an integrator has no steady-state gain")
    try:
        now_sig = plant_signature(spec, name)
    except Exception:
        now_sig = None
    if not isinstance(now_sig, str):
        return no("the system's signature could not be worked out")
    left, found = [], []
    for g in sigs:
        for t in tests_in(p, g, 0, now):
            why = _unusable(t, name, now_sig)
            if why:
                left.append({"goal": g, "test": t["id"], "why": why})
            else:
                found.append((g, t))
    found.sort(key=lambda x: x[1].get("seq") or 0)                  # record order, never by time
    du, dy, own = [], [], set()
    for g, t in found[-MOST_TESTS:]:
        got = _moves(p, sigs, t)
        if isinstance(got, str):
            left.append({"goal": g, "test": t["id"], "why": got})
            continue
        du.append(got[0])
        dy.append(got[1])
        own.add(g)
    goals = list(sigs)
    if len(du) < len(goals):
        return {**no(f"{len(du)} usable step tests, fewer than its {len(goals)} loops"), "left": left}
    if missing := [g for g in goals if g not in own]:
        return {**no(f"no usable step test of its own: {', '.join(missing)}"), "left": left}
    return {**solve(du, dy, goals), "left": left}


def line(r: dict | None) -> str | None:
    """What ``explain system.NAME`` says of it, one line (none for a system of fewer than two loops)."""
    if r is None:
        return None
    if not r["computed"]:
        out = f"Relative gain array: not computed: {r['why']}"
    else:
        lam = ", ".join(f"{g} {r['lambda'][i][i]:.2f}" for i, g in enumerate(r["goals"]))
        out = (f"Relative gain array: λ {lam} (each loop on its own u, from {r['tests']} step tests, the gains as held "
               f"over the last quarter of each hold)")
        out += "".join(f"; {x}" for x in r["notes"])
    if r.get("left"):
        out += f"; {len(r['left'])} tests left out: " + "; ".join(f"{x['test']} of {x['goal']}: {x['why']}"
                                                              for x in r["left"][:3])
    return out + "."
