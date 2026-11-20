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

Scaled errors closer than ``FLOOR`` are within the record's noise and count neither way. It **passes** a change
that is better by the threshold in every window that can tell, or that is no worse in any and answers
findings ``check`` reported (making none), or that is no worse and simpler (fewer parts, parameters and terms:
Occam) where the record replays what it touches (a part removed whose stocks nothing replays has no evidence for or
against it: that is inconclusive).
It **fails** one worse by the threshold in any window, near it, elsewhere or on a goal's measure, or better
only in some. One the record cannot tell from the model as it is (no window better or worse by the threshold) is
kept under test for more record, up to three times what it needs, then said **inconclusive**: needs more record,
not failed.

It does not vouch for what the record has not exercised: a value or an equation whose parts did not move in the
record held out (``exercised.py``) is never passed on it; it stays under test and is then inconclusive, needing
record in which they move.

What happens to a passed change is the judge's policy (``accept``, by kind): ``owner`` (the default) leaves it in
the review queue, its verdict beside it; ``auto`` writes it, as Accept does (the smallest edit, ``check`` must still
pass, recorded as ``ergostat.model-change.accepted`` from the judge, naming the policy, and
``ergostat.model.changed``), one a pass. Only a value, an equation or the structure is judged or written so: a
change to a goal, a block or a sensor waits for the owner, and so does any change that removes structure
(``removes``) or chains a kind's state stocks (``rewires``: a flow re-pointed or added between them), whatever the
policy. The owner commits what was written.

It is cheap when there is nothing new to judge: a change is looked at again only once its next window is due
(``needs`` past the last look) and what it touches has been read since (a record that stopped is not replayed
again, and the change waits for more); the model's time constants, replayed on the day before a change, are kept by
the model's content and the ten minutes the change was made in, for every change made against it meanwhile; and the
run backs off when the judge has nothing to judge (``pause``)."""

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
FLOOR = 0.005                 # scaled errors closer than this are within the record's noise: neither better nor worse
TAU_POINTS = 120              # the time constants are read from a replay of the reference window in this many buckets
PORTS = JUDGE_PORTS
IDLE_MOST = 8.0               # the judge, idle, waits at most this many of its every between passes


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


_TAU: dict = {}               # the model's time constants, by its content and the ten minutes of record they end in


def replayed(spec: Spec) -> str:
    """What a replay of the model reads of it (its stocks, flows, auxiliaries and parameters, with their sensors and
    numbers), as a short hash: two specs with the same one replay the same on the same record."""
    from . import version as ver
    return ver._hash([ver._plain(x) for x in (spec.stocks, spec.flows, spec.auxiliaries, spec.parameters)])


def dominant(p, spec: Spec, parts: list[str], until: float) -> float | None:
    """The slowest time constant (s) the replay meets among these parts (a stock's own drain, a delay's time) on the
    record up to ``until``; None when none of them has one (they only accumulate). The replay is the model's, whatever
    the parts: kept by the model's content and the ten minutes ``until`` falls in."""
    key = (str(p.dir), replayed(spec), int(until // 600))
    tc = _TAU.get(key)
    if tc is None:                               # one replay for every change made against this model meanwhile
        data = ob.measured(p, ob.reference(p, until, TAU_POINTS), spec)
        tc = dict(sim.replay(spec, data).time_constants)
        if len(_TAU) > 256:
            _TAU.clear()
        _TAU[key] = tc
    got = [tc[r] for r in parts if tc.get(r)]
    return max(got) * 3600.0 if got else None


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
    near = [r for r in common if r in set(stocks or ())]
    fallback = not near                         # nothing it touches is replayed: every stock, and no evidence about it
    near = near or common
    rest = [r for r in common if r not in near]
    b = _mean(sb, near) if sb is not None else None
    a = _mean(sa, near) if sa is not None else None
    rb, ra = (_mean(sb, rest), _mean(sa, rest)) if sb is not None and sa is not None else (None, None)
    out = {"since": since, "until": until, "before": b, "after": a, "change": _change(b, a), "scored": near,
           "fallback": fallback and bool(stocks),
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


def _apart(r: dict) -> bool:
    """The scaled errors differ by more than the record's noise (``FLOOR``), so a share of either says something."""
    return r.get("before") is None or r.get("after") is None or abs(r["before"] - r["after"]) > FLOOR


def _worst_elsewhere(r: dict, threshold: float) -> str | None:
    """Why a window is worse away from what the change touches: the rest of the model, or a goal's own measure."""
    if r.get("rest_change") is not None and r["rest_change"] <= -threshold and r["rest_after"] - r["rest_before"] > FLOOR:
        return f"the rest of the model {_pct(-r['rest_change'])} worse ({r['rest_before']:.3g} → {r['rest_after']:.3g})"
    for g, x in (r.get("goals") or {}).items():
        if x["change"] is not None and x["change"] <= -threshold and x["after"] - x["before"] > FLOOR:
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
    worse = [r for r in judged if r["change"] <= -threshold and _apart(r)]
    away = [(r, w) for r in judged if (w := _worst_elsewhere(r, threshold))]
    better = [r for r in judged if r["change"] >= threshold and _apart(r)]
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
    noise = [r for r in judged if not _apart(r)]
    if better and len(better) + len(noise) == n:          # better wherever the record can tell, never worse
        return "kept", (f"better in every one of {n} windows held out: near what it touches ({near}) the scaled error "
                        f"falls by {_pct(lo)} to {_pct(hi)} (the threshold is {_pct(threshold)}), and no worse elsewhere")
    if not better and answers and not new:
        return "kept", (f"no worse in any of {n} windows held out (within {_pct(threshold)}), and it answers {answers} "
                        f"finding{'s' if answers > 1 else ''} check reported, making none")
    if not better and simpler and not new and not any(r.get("fallback") for r in judged):
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
WORDING = ("description", "unit", "rename")            # what a reader is told: judged by check alone, not the record
REDESIGN = "redesign"                                  # a change set: judged by its scorecard (redesign.py)
WORDING_MOST = 20                                      # wording changes written in one pass (each is measured alone anyway)


def wording(x: dict) -> tuple[str, str]:
    """The verdict on a change of words (a description, a unit, a rename): the replay reads the same record alike, so
    it is judged by what ``check`` says of the model it leaves: passed when it makes no new finding (and says what it
    answers), failed when it makes one."""
    f = x.get("findings") or {}
    new, answered = [*(f.get("new") or []), *(f.get("notes_new") or [])], [*(f.get("answered") or []), *(f.get("notes_answered") or [])]
    what = {"description": "a description", "unit": "a unit", "rename": "a rename"}.get(x.get("kind"), "a change of words")
    if new:
        return "failed", f"{what} that makes {len(new)} new finding{'s' if len(new) > 1 else ''} ({', '.join(new[:3])})"
    return "passed", (f"{what}: the replay reads the record the same with it; it answers "
                      + (f"{len(answered)} finding{'s' if len(answered) > 1 else ''} or note{'s' if len(answered) > 1 else ''} "
                         f"check reported ({', '.join(answered[:3])})" if answered else "nothing check reported")
                      + ", and makes none")


def run(p, by: str = "judge", at: float | None = None, most: int = MOST) -> dict:
    """One pass of the judge over the changes waiting: start testing the new ones, judge those whose record held out
    is long enough, and write one passed change the policy lets it write. Returns what it moved."""
    spec: Spec = p.model.spec
    pol = spec.improve
    now = at or time.time()
    out = {p_: 0 for p_ in PORTS} | {"verdicts": [], "waiting": []}
    try:                                                    # what accepted changes predicted, against what happened
        from .predict import observe
        out["observed"] = observe(p, now)
    except Exception:
        out["observed"] = 0
    for pid in pr.supersede(p, spec):
        out["verdicts"].append({"id": pid, "verdict": "superseded", "why": "the model changed since it was made"})
    judged = 0
    with pr.locked(p):
        for x in sorted(pr.pending(p, spec), key=lambda x: x.get("created") or 0):
            if x.get("kind") == REDESIGN:                    # a change set: judged as a whole, by its scorecard on the record
                if x["state"] == "checked":
                    from . import redesign as rd
                    try:
                        verdict, why, card = rd.judged(p, x, now)
                    except tr.TrialError as e:
                        pr.event(p, x["id"], "superseded", {"why": f"its edit no longer applies ({e})"})
                        out["verdicts"].append({"id": x["id"], "verdict": "superseded", "why": str(e)})
                        continue
                    pr.event(p, x["id"], "testing", {"testing": now, "judged_by": by})
                    out["testing"] += 1
                    pr.event(p, x["id"], verdict, {"verdict": {"verdict": verdict, "why": why, "at": now, "by": by},
                                                   **({"scorecard": card} if card else {})})
                    out[verdict] += 1
                    out["verdicts"].append({"id": x["id"], "verdict": verdict, "why": why})
                continue
            if x["state"] != "passed" and x.get("kind") in WORDING:
                verdict, why = wording(x)
                if x["state"] == "checked":                  # tested like any change, on what check says of it
                    pr.event(p, x["id"], "testing", {"testing": now, "judged_by": by})
                    out["testing"] += 1
                pr.event(p, x["id"], verdict, {"verdict": {"verdict": verdict, "why": why, "at": now, "by": by}})
                out[verdict] += 1
                out["verdicts"].append({"id": x["id"], "verdict": verdict, "why": why})
                continue
            if x["state"] == "passed" or x.get("kind") not in JUDGED:
                continue
            since = x.get("made") or x.get("created") or now
            looked = float(x.get("looked") or 0.0)            # the record judged when it was last looked at
            if x["state"] == "testing" and x.get("hold_out"):  # under test: nothing to do before its next window
                due = max(float(x["hold_out"]), looked + float(x["hold_out"]))
                if now - since < due or judged >= most:
                    out["waiting"].append({"id": x["id"], "held": now - since, "needs": due})
                    continue
            try:
                after = tr.spec_after(p, tr.edits_of(x))
            except tr.TrialError as e:
                pr.event(p, x["id"], "superseded", {"why": f"its edit no longer applies ({e})"})
                out["verdicts"].append({"id": x["id"], "verdict": "superseded", "why": str(e)})
                continue
            nd = needs(p, spec, after, x, since, pol.hold_out, pol.warm_up)
            if x["state"] == "checked":
                pr.event(p, x["id"], "testing", {"testing": now, "hold_out": nd["needs"], "judged_by": by,
                                                  "judging": {k: nd[k] for k in ("stocks", "goals", "tau", "warm_up", "needs")}})
                out["testing"] += 1
            held = now - since
            reach = recorded(p, spec, nd["stocks"], now)
            stalled = reach is not None and reach <= since + looked     # no reading of what it touches since the last look
            if held < nd["needs"] or held < looked + nd["needs"] or judged >= most or stalled:
                due = max(nd["needs"], looked + nd["needs"])
                out["waiting"].append({"id": x["id"], "held": now - since, "needs": due,
                                       **({"record": reach - since} if stalled else {})})
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
            q = quiet_held(p, spec, x, since, now)
            if q is not None and got[0] == "kept":            # it does not vouch for what the record has not exercised
                got = None if held < GIVE_UP * nd["needs"] else ("inconclusive", q)
                if got is None:
                    pr.event(p, x["id"], "testing", {"looked": held, "not_exercised": q})
                    out["waiting"].append({"id": x["id"], "held": held, "needs": held + nd["needs"], "judged": len(results)})
                    continue
            verdict, why = got
            state = {"kept": "passed", "dropped": "failed"}.get(verdict, verdict)
            pr.event(p, x["id"], state, {"verdict": {"verdict": state, "why": why, "at": now, "threshold": pol.threshold,
                                                      "windows": results, "held": held, "by": by, "warm_up": nd["warm_up"],
                                                      "tau": nd["tau"], "needs": nd["needs"], "scored": nd["stocks"]}})
            out[state] += 1
            out["verdicts"].append({"id": x["id"], "verdict": state, "why": why})
    words = 0
    sets = [y for y in pr.pending(p, spec) if y.get("kind") == REDESIGN]     # a redesign waiting: nothing written over it
    from . import redesign as rd
    if rd.running(p, now, rd.HOLD_FOR):          # a redesign being made: the model it reads held still, for a while
        return out
    first = [y for y in sets if y["state"] == "passed" and pol.accept.get(REDESIGN) == "auto" and not owners(y)][:1]
    held = sets if pol.accept.get(REDESIGN) == "auto" else []   # a redesign the judge may write holds its lines; one
    # only the owner writes holds nothing (it is carried, or superseded, as the model moves)
    todo = first + [y for y in sorted(pr.pending(p, spec), key=lambda x: x.get("created") or 0) if y not in first]
    for x in todo:                                   # a redesign the owner promoted and the judge passed is written first,
        if x["state"] != "passed" or x.get("kind") not in (*JUDGED, *WORDING, REDESIGN) or pol.accept.get(x.get("kind")) != "auto":
            continue                                 # alone; else one a pass, the oldest first (words as many as passed)
        if owners(x):                                # a removal, a chain rewired, a redesign's control: the owner's
            continue
        if x.get("kind") != REDESIGN and any(tr.conflicts(x, y) for y in held):
            continue
        if x.get("kind") in WORDING and words >= WORDING_MOST:
            continue
        snap = {"at": now, "window": ob.reference(p, now).until - ob.reference(p, now).since}
        try:
            pr.accept(p, x["id"], snap, by=by, why=f"the judge passed it: {(x.get('verdict') or {}).get('why')}",
                      policy=f"judge {by}: accept {x['kind']}: auto")
        except pr.ProposalError as e:
            if x.get("kind") == REDESIGN:            # a promoted redesign that cannot be written never blocks the rest
                pr.event(p, x["id"], "superseded", {"why": f"it could not be written: {e}"})
                held = [y for y in held if y["id"] != x["id"]]
                out["verdicts"].append({"id": x["id"], "verdict": "superseded", "why": f"not written: {e}"})
                continue
            out["verdicts"].append({"id": x["id"], "verdict": "passed", "why": f"not written: {e}"})
            continue
        out["accepted"] += 1
        if x.get("kind") in WORDING:                       # words are written as many a pass as there are: the rest's
            words += 1                                     # lines moved with them (proposals.rebase)
            spec = p.model.spec
            continue
        break
    return out


def recorded(p, spec: Spec, stocks: list[str], now: float) -> float | None:
    """How far the record of these stocks reaches (their sensors' newest reading, up to ``now``); None when none of
    them is read by a sensor."""
    out = None
    for ref in stocks:
        st = spec.stocks.get(ref.split(".", 1)[1]) if ref.startswith("stock.") else None
        for s in (st.sensors.values() if st is not None else ()):
            got = p.measurements.latest(s.series, now)
            if got and (out is None or got[0] > out):
                out = got[0]
    return out


def pause(got: dict, every: float, idle: int) -> float:
    """How long the judge waits before its next pass, after one that returned ``got`` (``idle``: the passes in a row
    before it that moved nothing): its ``every`` when it moved something, or a change is due by the clock; else
    until the first change waiting is due, or longer each idle pass, never more than ``IDLE_MOST`` times its every."""
    if got.get("verdicts") or any(got.get(k) for k in PORTS):
        return every
    longest = every * IDLE_MOST
    due = [w["needs"] - w["held"] for w in got.get("waiting") or [] if "record" not in w]
    if due:
        return min(longest, max(every, min(due)))
    return min(longest, every * 2 ** (idle + 1))


def owners(x: dict) -> bool:
    """A change only the owner writes, whatever the policy (SPEC §12e, ``accept``): one that takes structure away or
    rewires a kind's chain, and a redesign that changes control."""
    return removes(x) or bool(x.get("rewires")) or (x.get("kind") == REDESIGN and bool(x.get("control")))


def removes(x: dict) -> bool:
    """A change that takes structure away: never written by the judge's policy; the owner decides. A rename takes no
    part away (each keeps its history under its new name)."""
    if x.get("kind") == "rename":
        return bool(x.get("removes"))
    return bool(x.get("removes") or x.get("gone_parts"))


def quiet_held(p, spec: Spec, x: dict, since: float, until: float) -> str | None:
    """Why the record held out cannot vouch for a value or an equation, or None: every part it acts through (a
    parameter's users, an equation's flow) that the record reads is not exercised there (``exercised.py``)."""
    from . import exercised as ex
    if x.get("kind") not in ("parameter", "equation") or until - since < MIN_WINDOW:
        return None
    refs = [*(x.get("parts") or []), *(f"parameter.{n}" for n in x.get("parameters") or {}), x.get("target")]
    via = list(dict.fromkeys(u for r in refs if r for u in (ex.users(spec, r[10:]) if r.startswith("parameter.") else [r])
                             if u.split(".")[0] in ("flow", "auxiliary")))
    if not via:
        return None
    g = ob.Grid(since, until, max(2, min(series.POINTS, int((until - since) // ob.MIN_BUCKET))))
    data = ob.measured(p, g, spec)
    q = ex.quiet(spec, data, least=MIN_WINDOW, readings=MIN_JUDGED * 4)
    read = [r for r in via if any(v is not None for v in data.values.get(r) or []) and data.how.get(r) not in ("declared", "not measured")]
    if not read or any(r not in q for r in read):
        return None
    w = q[read[0]]
    return (f"the record held out has not exercised what it acts through ({', '.join(read)}: {w['says']} over "
            f"{dur(until - since)}): no record can vouch for its rate yet, and none says it is wrong; it needs record "
            f"in which {read[0].split('.', 1)[1]} moves ({ex.SUGGEST})")


def lines(spec: Spec, block: str | None, got: dict) -> list[dict]:
    """What its block reports: what it moved on each port it has."""
    b = spec.blocks.get(block or "")
    if b is None:
        return []
    return [{"out": port, "moved": got[port]} for port in PORTS if port in b.outputs]
