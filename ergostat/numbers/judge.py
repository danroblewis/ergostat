"""The judge of changes to the model (SPEC §12e), a built-in block (``type: judge``, on the program rung), as
image-squeeze's rollout judges a build: each change waiting (``ergostat.model-change`` items checked, whoever made
them: a block's propose line, ergostat's own finders, the owner's what-if) is replayed beside the model as it is on
the record that came **after** it was made, which neither its maker nor any estimate it rests on has seen, over
several windows of several durations (the whole of that record, and its halves, quarters, ..., as ``windows``
says).

It scores **what the change touches**: the stocks of its neighbourhood (``gate.stocks_of``: what it changes, a
parameter's users and their stocks, one link on), the goals' own stocks among them, not the whole model's mean,
where one far stock's error would dilute any change to nothing. The rest of the model must be no worse. It waits
for record **long enough for the change to show**: at least its hold-out and the dominant time constant of what it
touches, at most a day; each window is replayed warm, from a few of those time constants before it, never longer
than the configured ``warm-up`` nor than the record held before it (on a young record a six-hour warm-up integrated
the stocks from where the record did not reach, and scored in a regime of its own).

It **passes** a change that is better by the threshold in every window, or that is no worse in any and answers
findings ``check`` reported (making none), or that is no worse and simpler (fewer parts, parameters and terms:
Occam). It **fails** one worse by the threshold in any window, near it, elsewhere or on a goal's measure, or better
only in some. One the record cannot tell from the model as it is (no window better or worse by the threshold) is
kept under test for more record, up to three times what it needs, then said **inconclusive**: needs more record,
not failed.

What happens to a passed change is the judge's policy (``accept``, by kind): ``owner`` (the default) leaves it in
the review queue, its verdict beside it; ``auto`` writes it, as Accept does (the smallest edit, ``check`` must still
pass, recorded as ``ergostat.model-change.accepted`` from the judge, naming the policy, and
``ergostat.model.changed``), one a pass. Only a value, an equation or the structure is judged or written so: a
change to a goal, a block or a sensor waits for the owner. The owner commits what was written."""

from __future__ import annotations

import time

from .. import series
from ..durations import human as dur
from ..spec.ir import JUDGE_PORTS, Spec
from . import gate as gt
from . import observe as ob
from . import proposals as pr
from . import simulate as sim
from . import trial as tr

SPLITS = (1, 2, 4)            # the record held out, whole, in halves and in quarters
MIN_WINDOW = 60.0             # a window shorter than this (s) is not judged
MIN_JUDGED = 3                # windows judged before a verdict
GIVE_UP = 3.0                 # after this many hold-outs with too few windows judged: dropped, too little record
MOST = 3                      # candidates judged in one run
WARM_UP = 6 * 3600.0          # each window is replayed from at most this long before it (improve.warm-up)
WARM_TAUS = 3.0               # ... and from this many of the dominant time constant before it, when that is less
MAX_HOLD = ob.REFERENCE       # the most record a change waits for, however slow what it touches
TAU_POINTS = 120              # the time constants are read from a replay of the reference window in this many buckets
PORTS = JUDGE_PORTS


def windows(since: float, until: float, splits=SPLITS, least: float = MIN_WINDOW) -> list[tuple[float, float]]:
    """The record held out, whole and split, each window at least ``least`` long (a minute, or the dominant time
    constant of what the change touches: a shorter window cannot show its effect)."""
    out = []
    span = until - since
    for k in splits:
        w = span / k
        if w < max(MIN_WINDOW, least):
            continue
        out += [(since + i * w, since + (i + 1) * w) for i in range(k)]
    return out


def _grid(since: float, until: float) -> ob.Grid:
    return ob.Grid(since, until, max(2, min(series.POINTS, int((until - since) // ob.MIN_BUCKET))))


def per_stock(spec: Spec, data: ob.Data, run, first: int = 0) -> dict[str, float]:
    """Each stock's scaled error (its mean squared error over the record's mean square) from bucket ``first`` on,
    whatever its time constant: the fit's total leaves out a stock whose replay is slower than the window is long,
    so a change that slowed a stock enough would take it out of the total, and look better."""
    from . import fit as ft
    out = {}
    for ref in run.how:
        if not ref.startswith("stock."):
            continue
        got = [(m, a) for i, m, a in ft.pairs(spec, data, run, ref) or [] if i >= first]
        if len(got) < 5:
            continue
        mse = sum((m - a) ** 2 for m, a in got) / len(got)
        scale = sum(a * a for _, a in got) / len(got)
        out[ref] = mse / (scale or 1.0)
    return out


def focus(spec: Spec, after: Spec, x: dict) -> dict:
    """What a change touches, for the judge: the stocks of its neighbourhood in the model as it is and with the
    change, the goals that hold one of them, and the parts whose time constants say how long its effect takes."""
    refs = [r for r in [*(x.get("parts") or []), *(x.get("touched") or []), *str(x.get("target") or "").split(", "),
                        *(x.get("new_parts") or []), *(x.get("gone_parts") or [])] if r]
    stocks = sorted(set(gt.stocks_of(spec, refs)) | set(gt.stocks_of(after, refs)))
    goals = {f"stock.{g.of.name}": n for n, g in spec.goals.items() if g.of.kind == "stock" and f"stock.{g.of.name}" in stocks}
    parts = sorted(gt.touched(spec, refs) | gt.touched(after, refs) | set(stocks))
    return {"stocks": stocks, "goals": goals, "parts": parts}


_TAU: dict = {}


def dominant(p, spec: Spec, parts: list[str], until: float) -> float | None:
    """The slowest time constant (s) the replay meets among these parts (a stock's own drain, a delay's time) on the
    record up to ``until``; None when none of them has one (they only accumulate)."""
    from . import version as ver
    key = (str(p.dir), ver.version(spec), tuple(parts), int(until // 600))
    if key in _TAU:
        return _TAU[key]
    data = ob.measured(p, ob.reference(p, until, TAU_POINTS), spec)
    run = sim.replay(spec, data)
    taus = [run.time_constants[r] for r in parts if run.time_constants.get(r)]
    got = max(taus) * 3600.0 if taus else None
    if len(_TAU) > 256:
        _TAU.clear()
    _TAU[key] = got
    return got


def needs(p, spec: Spec, after: Spec, x: dict, since: float, hold_out: float, warm_up: float) -> dict:
    """How much record after the change it is judged on, and how long each window's warm-up is: at least the hold-out
    and the dominant time constant of what it touches in the model as it is, at most a day; warmed up for a few time
    constants (with the change too), never longer than the configured warm-up nor the record before it, and not at
    all when nothing it touches has a time constant (its stocks only accumulate: there is nothing to settle).
    Each window is at least that time constant long, so the record it needs holds ``MIN_JUDGED`` of them: twice it."""
    fc = focus(spec, after, x)
    tau = dominant(p, spec, fc["parts"], since)              # the record's dynamics, as the model sees them
    with_it = dominant(p, after, fc["parts"], since)         # a change that slows a part buys no more time to be judged in,
    warm_tau = max((t for t in (tau, with_it) if t), default=None)   # but its delays are warmed up
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=since)
    held_before = max(0.0, since - oldest)
    warm = min(warm_up, held_before, WARM_TAUS * warm_tau) if warm_tau else 0.0   # what only accumulates has nothing to
    # settle: started at its first reading in the window it is exact, where hours of warm-up integrate drift into it
    need = min(MAX_HOLD, max(hold_out, 2 * (tau or 0.0)))
    return {**fc, "tau": tau, "tau_with_it": with_it, "warm_up": warm, "needs": need, "record_before": held_before}


def scored(p, spec: Spec, since: float, until: float, warm_up: float = WARM_UP) -> dict[str, float] | None:
    """Each stock's scaled error over [since, until], on a replay started ``warm_up`` seconds before it (so its stocks
    and delays are as the record left them, not started cold, every delay in equilibrium, at the window's first
    reading); None when that replay is not valid."""
    start = since - warm_up
    width = max(ob.MIN_BUCKET, (until - since) / 30.0)
    grid = ob.Grid(start, until, max(2, int(round((until - start) / width))))
    data = ob.measured(p, grid, spec)
    run = sim.replay(spec, data)
    if not run.valid:
        return None
    return per_stock(spec, data, run, int((since - start) // grid.width))


def _mean(xs: dict[str, float], refs) -> float | None:
    got = [xs[r] for r in refs if r in xs]
    return sum(got) / len(got) if got else None


def _change(b: float | None, a: float | None) -> float | None:
    """The share by which the change lowers a scaled error (negative: raises it); a trifle either way is none."""
    if b is None or a is None:
        return None
    if abs(b - a) <= gt.TRIFLE * 1e-2:
        return 0.0
    return (b - a) / b if b else (0.0 if a == 0 else -1.0)


def compare(p, spec: Spec, after: Spec, since: float, until: float, warm_up: float = WARM_UP,
            stocks: list[str] | None = None, goals: dict[str, str] | None = None) -> dict:
    """The model as it is and with the change, replayed on one window (each warmed up beforehand): the scaled error
    near what it touches (``stocks``, over those both replay; every stock when none is given or none is replayed),
    the rest's, each goal's own stock's, and the share by which the change lowers each (negative: raises it)."""
    sb, sa = scored(p, spec, since, until, warm_up), scored(p, after, since, until, warm_up)
    common = sorted(set(sb or {}) & set(sa or {}))
    near = [r for r in common if r in set(stocks or ())] or common
    rest = [r for r in common if r not in near]
    b = _mean(sb, near) if sb is not None else None
    a = _mean(sa, near) if sa is not None else None
    rb, ra = (_mean(sb, rest), _mean(sa, rest)) if sb is not None and sa is not None else (None, None)
    out = {"since": since, "until": until, "before": b, "after": a, "change": _change(b, a), "scored": near,
           "rest_before": rb, "rest_after": ra, "rest_change": _change(rb, ra) if rest else None}
    if goals and sb is not None and sa is not None:
        out["goals"] = {g: {"stock": r, "before": sb[r], "after": sa[r], "change": _change(sb[r], sa[r])}
                        for r, g in goals.items() if r in sb and r in sa}
    return out


def complexity(spec: Spec) -> int:
    """How much a model says: its parts, its parameters, and the terms of its equations."""
    from ..spec import equation as eq
    terms = 0
    for t in (spec.flows, spec.auxiliaries):
        for x in t.values():
            if x.equation:
                terms += len(eq.refs(x.equation.tree)) + len(x.equation.parameters) + 1
    return len(spec.stocks) + len(spec.flows) + len(spec.auxiliaries) + len(spec.parameters) + terms


def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def _worst_elsewhere(r: dict, threshold: float) -> str | None:
    """Why a window is worse away from what the change touches: the rest of the model, or a goal's own measure."""
    if r.get("rest_change") is not None and r["rest_change"] <= -threshold:
        return f"the rest of the model {_pct(-r['rest_change'])} worse ({r['rest_before']:.3g} → {r['rest_after']:.3g})"
    for g, x in (r.get("goals") or {}).items():
        if x["change"] is not None and x["change"] <= -threshold:
            return f"goal {g}'s {x['stock']} {_pct(-x['change'])} worse ({x['before']:.3g} → {x['after']:.3g})"
    return None


def decide(results: list[dict], threshold: float, answers: int, new: int, held: float, hold_out: float,
           simpler: bool = False) -> tuple[str, str] | None:
    """The verdict, kept, dropped or inconclusive, with why; or None: keep testing (``hold_out``: the record the
    change needs; it waits up to ``GIVE_UP`` times that for a window that can tell it)."""
    judged = [r for r in results if r["change"] is not None]
    n = len(judged)
    if n < MIN_JUDGED:
        if held < GIVE_UP * hold_out:
            return None
        if answers and not new and not judged:
            return "kept", (f"nothing it changes is fitted, so the record cannot judge it; it answers {answers} finding"
                            f"{'s' if answers > 1 else ''} check reported, and makes none")
        return "inconclusive", (f"too little record to judge it: {n} window{'s' if n != 1 else ''} with a fit in "
                                f"{dur(held)} held out (at least {MIN_JUDGED} are needed); it needs more record")
    worse = [r for r in judged if r["change"] <= -threshold]
    away = [(r, w) for r in judged if (w := _worst_elsewhere(r, threshold))]
    better = [r for r in judged if r["change"] >= threshold]
    lo, hi = min(r["change"] for r in judged), max(r["change"] for r in judged)
    sc = judged[0].get("scored") or []
    near = (", ".join(sc[:4]) + (f" and {len(sc) - 4} more" if len(sc) > 4 else "")) or "every stock"
    if worse:
        w = min(worse, key=lambda r: r["change"])
        return "dropped", (f"worse in {len(worse)} of {n} windows held out: near what it touches ({near}) the scaled error "
                           f"rises by up to {_pct(-w['change'])} ({w['before']:.3g} → {w['after']:.3g} over "
                           f"{dur(w['until'] - w['since'])})")
    if away:
        r, why = away[0]
        return "dropped", (f"worse elsewhere in {len(away)} of {n} windows held out: {why} over {dur(r['until'] - r['since'])}, "
                           f"though near what it touches ({near}) {_pct(r['change'])} better")
    if len(better) == n:
        return "kept", (f"better in every one of {n} windows held out: near what it touches ({near}) the scaled error "
                        f"falls by {_pct(lo)} to {_pct(hi)} (the threshold is {_pct(threshold)}), and no worse elsewhere")
    if not better and answers and not new:
        return "kept", (f"no worse in any of {n} windows held out (within {_pct(threshold)}), and it answers {answers} "
                        f"finding{'s' if answers > 1 else ''} check reported, making none")
    if not better and simpler and not new:
        return "kept", (f"simpler, and no worse in any of {n} windows held out (within {_pct(threshold)}, near what it "
                        f"touches: {near}, and elsewhere)")
    if not better and not new:
        if held < GIVE_UP * hold_out:
            return None
        return "inconclusive", (f"the record cannot tell it from the model as it is: within {_pct(threshold)} in every one of "
                                f"{n} windows held out, near what it touches ({near}: from {_pct(lo)} to {_pct(hi)}), over "
                                f"{dur(held)}; it needs more record, of a time when what it touches moves")
    return "dropped", (f"not consistently better: by {_pct(threshold)} or more in {len(better)} of {n} windows held out "
                       f"(from {_pct(lo)} to {_pct(hi)}, near what it touches: {near})"
                       + (f"; it makes {new} new finding{'s' if new > 1 else ''}" if new else ""))


def _event(p, x: dict, what: str, by: str, data: dict) -> None:
    p.events.add(f"model.{what}", item=f"proposal/{x['id']}", source=by, data={"title": x["title"], **data})


JUDGED = ("parameter", "equation", "structure")        # what a replay can judge (a loop's process or gain is not)


def run(p, by: str = "judge", at: float | None = None, most: int = MOST) -> dict:
    """One pass of the judge over the changes waiting: start testing the new ones, judge those whose record held out
    is long enough, and write one passed change the policy lets it write. Returns what it moved."""
    spec: Spec = p.model.spec
    pol = spec.improve
    now = at or time.time()
    out = {p_: 0 for p_ in PORTS} | {"verdicts": [], "waiting": []}
    for pid in pr.supersede(p, spec):
        out["verdicts"].append({"id": pid, "verdict": "superseded", "why": "the model changed since it was made"})
    judged = 0
    with pr.locked(p):
        for x in sorted(pr.pending(p, spec), key=lambda x: x.get("created") or 0):
            if x["state"] == "passed" or x.get("kind") not in JUDGED:
                continue
            try:
                after = tr.spec_after(p, tr.edits_of(x))
            except tr.TrialError as e:
                pr.event(p, x["id"], "superseded", {"why": f"its edit no longer applies ({e})"})
                out["verdicts"].append({"id": x["id"], "verdict": "superseded", "why": str(e)})
                continue
            since = x.get("made") or x.get("created") or now
            nd = needs(p, spec, after, x, since, pol.hold_out, pol.warm_up)
            if x["state"] == "checked":
                pr.event(p, x["id"], "testing", {"testing": now, "hold_out": nd["needs"], "judged_by": by,
                                                  "judging": {k: nd[k] for k in ("stocks", "goals", "tau", "warm_up", "needs")}})
                out["testing"] += 1
            held = now - since
            looked = float(x.get("looked") or 0.0)            # held, when it was last looked at and could not be told
            if held < nd["needs"] or held < looked + nd["needs"] or judged >= most:
                out["waiting"].append({"id": x["id"], "held": held, "needs": max(nd["needs"], looked + nd["needs"])})
                continue
            judged += 1
            results = [compare(p, spec, after, a, b, nd["warm_up"], nd["stocks"], nd["goals"])
                       for a, b in windows(since, now, pol.windows, min(nd["tau"] or 0.0, nd["needs"] / 2))]
            f = x.get("findings") or {}
            got = decide(results, pol.threshold, len(f.get("answered") or []), len(f.get("new") or []), held, nd["needs"],
                         simpler=complexity(after) < complexity(spec))
            if got is None:
                pr.event(p, x["id"], "testing", {"looked": held})
                out["waiting"].append({"id": x["id"], "held": held, "needs": held + nd["needs"], "judged": len(results)})
                continue
            verdict, why = got
            state = {"kept": "passed", "dropped": "failed"}.get(verdict, verdict)
            pr.event(p, x["id"], state, {"verdict": {"verdict": state, "why": why, "at": now, "threshold": pol.threshold,
                                                      "windows": results, "held": held, "by": by, "warm_up": nd["warm_up"],
                                                      "tau": nd["tau"], "needs": nd["needs"], "scored": nd["stocks"]}})
            out[state] += 1
            out["verdicts"].append({"id": x["id"], "verdict": state, "why": why})
    for x in sorted(pr.pending(p, spec), key=lambda x: x.get("created") or 0):     # one written a pass, the oldest first
        if x["state"] != "passed" or x.get("kind") not in JUDGED or pol.accept.get(x.get("kind")) != "auto":
            continue
        snap = {"at": now, "window": ob.reference(p, now).until - ob.reference(p, now).since}
        try:
            pr.accept(p, x["id"], snap, by=by, why=f"the judge passed it: {(x.get('verdict') or {}).get('why')}",
                      policy=f"judge {by}: accept {x['kind']}: auto")
        except pr.ProposalError as e:
            out["verdicts"].append({"id": x["id"], "verdict": "passed", "why": f"not written: {e}"})
            continue
        out["accepted"] += 1
        break
    return out


def lines(spec: Spec, block: str | None, got: dict) -> list[dict]:
    """What its block reports: what it moved on each port it has."""
    b = spec.blocks.get(block or "")
    if b is None:
        return []
    return [{"out": port, "moved": got[port]} for port in PORTS if port in b.outputs]
