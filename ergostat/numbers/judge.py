"""The judge of changes to the model (SPEC §12e), a built-in block (``type: judge``, on the program rung), as
image-squeeze's rollout judges a build: each change waiting (``ergostat.model-change`` items checked, whoever made
them: a block's propose line, ergostat's own finders, the owner's what-if) is replayed beside the model as it is on
the record that came **after** it was made, which neither its maker nor any estimate it rests on has seen: each
replayed once over all of that record, warm, and paired with it reading by reading.

It scores **what the change touches**: the stocks of its neighbourhood (``gate.stocks_of``: what it changes, a
parameter's users and their stocks, one link on), the goals' own stocks among them, not the whole model's mean,
where one far stock's error would dilute any change to nothing. The rest of the model must be no worse. It waits
for record **long enough for the change to show**: at least its hold-out and the dominant time constant of what it
touches, at most a day; the replay is warm, from a few of those time constants before it, never longer than the
configured ``warm-up`` nor than the record held before it (on a young record a six-hour warm-up integrated the stocks
from where the record did not reach, and scored in a regime of its own).

**The evidence is pooled, and its error rate stated** (``pooled``). At each reading the two scaled errors differ by
δ(δ + 2(after − record)), δ what the change moves the replay by: known exactly, so the only noise is the record's
own about the better replay, taken as AR(1) (its correlation from one reading to the next, and from a twelfth of the
record on; while the record spans fewer than three time constants of what the change touches, noise that drifts is
taken to last that long; what only accumulates, with no time constant, as a walk as well; a bias in the better replay
counts as noise). Several stocks' noises may be correlated: their standard errors add. Errors within ``FLOOR`` count
neither way. That gives the change's effect (the share by which it lowers the scaled error) and its standard error,
and a **confidence sequence** (a normal mixture) bounds it, in units of the record the change needs. It is a plug-in,
asymptotic sequence, valid under stationary AR(1) noise (or a walk) read well enough from the record: then, however
often the judge looks as the record grows, a change no better than the model as it is passes at most about ``ALPHA``
of the time and one no worse fails at most about that (two-sided at 2·ALPHA by Ville's inequality, each way ALPHA by
the noise's symmetry; the fail side's several tests, near it, elsewhere and each goal's stock, share ALPHA:
Bonferroni). Measured on records made to that model: at most 5% passed, 6% failed (``tests/test_slowjudge.py``).
It **passes** a change whose
bound's low end is above no change and that is better by the threshold, near it, and no worse elsewhere or on a goal's
stock; or one the bound holds no worse (within the threshold) that answers findings ``check`` reported (making none),
or that is simpler (fewer parts, parameters and terms: Occam) where the record replays what it touches. It **fails**
one whose bound's high end is below no change and that is worse by the threshold, near it, elsewhere or on a goal's
stock. One the bound holds within the threshold both ways is said **inconclusive** once it has three times the record
it needs: the record tells it from the model as it is by less than that. One whose replay is the same as the model's
waits for record in which what it touches moves. One the bound cannot decide yet says **about how much more record it
needs** (the bound narrows as one over the root of the record), and stays under test until seven times the record it
needs, a day at least (``horizon``), then is inconclusive, saying how much more. The verdict keeps the record whole,
in halves and in quarters (``windows``), sliced from the same replay, for its reader.

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

It is cheap when there is nothing new to judge: a change is looked at again only once its next look is due
(``due``: the record it needs, or a quarter more, past the last look) and what it touches has been read since (a
record that stopped is not replayed again, and the change waits for more); the model's time constants, replayed on
the day before a change, are kept by the model's content and the ten minutes the change was made in, for every change
made against it meanwhile; and the run backs off when the judge has nothing to judge (``pause``)."""

from __future__ import annotations

import math
import time

from .. import series
from ..durations import human as dur
from ..spec.ir import JUDGE_PORTS, Spec
from . import gate as gt
from . import observe as ob
from . import proposals as pr
from . import simulate as sim
from . import trial as tr
from .improve import WORDING  # what a reader is told: judged by check alone, not the record

SPLITS = (1, 2, 4)            # the record held out, whole, in halves and in quarters
MIN_WINDOW = 60.0             # a window shorter than this (s) is not judged
GIVE_UP = 3.0                 # it waits this many times the record it needs before saying the record cannot tell it
ALPHA = 0.05                  # the most often a change no better than the model as it is is passed (and one no worse failed),
#                               however often it is looked at
FLOOR = 0.005                 # scaled errors that stay within this of each other, bound and all, count neither way
MIX = 1.0                     # the bound's mixture scale, in units of the record a change needs: tightest about there
SPANS = 3.0                   # ... while the record spans fewer than this many of the time constant
DRIFTS = 0.5                  # noise correlated this much from one bucket to the next drifts: the time constant bounds it
RHO_MAX = 0.995               # the record's noise correlation from one reading to the next, at most
LONGEST = 7.0                 # one the bound cannot decide stays under test up to this many times the record it needs,
#                               and a day at least (horizon)
MOST = 3                      # candidates judged in one run
WARM_UP = 6 * 3600.0          # each window is replayed from at most this long before it (improve.warm-up)
WARM_TAUS = 3.0               # ... and from this many of the dominant time constant before it, when that is less
MAX_HOLD = ob.REFERENCE       # the most record a change waits for, however slow what it touches
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


def readings(spec: Spec, data: ob.Data, run, first: int = 0) -> dict[str, dict[int, tuple[float, float]]]:
    """Each stock's replay and record at each bucket with a reading from bucket ``first`` on (five at least)."""
    from . import fit as ft
    out = {}
    for ref in run.how:
        got = [(i, m, a) for i, m, a in ft.pairs(spec, data, run, ref) or [] if i >= first] if ref.startswith("stock.") else []
        if len(got) >= 5:
            out[ref] = {i: (m, a) for i, m, a in got}
    return out


def per_stock(spec: Spec, data: ob.Data, run, first: int = 0) -> dict[str, float]:
    """Each stock's scaled error (its mean squared error over the record's mean square) from bucket ``first`` on,
    whatever its time constant: the fit's total leaves out a stock whose replay is slower than the window is long,
    so a change that slowed a stock enough would take it out of the total, and look better."""
    out = {}
    for ref, got in readings(spec, data, run, first).items():
        out[ref] = sum((m - a) ** 2 for m, a in got.values()) / (sum(a * a for _, a in got.values()) or 1.0)
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


def compare(p, spec: Spec, after: Spec, since: float, until: float, warm_up: float = WARM_UP,
            stocks: list[str] | None = None, goals: dict[str, str] | None = None,
            taus: tuple[float | None, float | None] = (None, None)) -> dict:
    """The model as it is and with the change, each replayed once over [since, until] (warmed up beforehand), paired
    with the record bucket by bucket: near what it touches (``stocks``, over those both replay; every stock when none
    is given or none is replayed), the rest of the model, and each goal's own stock. Each stock's rows are (bucket,
    before, after, record), scaled by the record's root mean square, so their squared errors are its scaled error."""
    start = since - warm_up
    width = max(ob.MIN_BUCKET, (until - since) / 120, (until - start) / 600)
    grid = ob.Grid(start, until, max(2, int(round((until - start) / width))))
    first = int((since - start) // grid.width)
    got = []
    for s in (spec, after):
        data = ob.measured(p, grid, s)
        run = sim.replay(s, data)
        got.append(readings(s, data, run, first) if run.valid else {})
    rb, ra = got
    paired = {}
    for r in sorted(set(rb) & set(ra)):
        both = sorted(set(rb[r]) & set(ra[r]))
        sc = math.sqrt(sum(rb[r][i][1] ** 2 for i in both) / len(both) or 1.0) if both else 1.0
        if len(both) >= 5:
            paired[r] = [(i, rb[r][i][0] / sc, ra[r][i][0] / sc, rb[r][i][1] / sc) for i in both]
    near = [r for r in paired if r in set(stocks or ())]
    out = {"since": since, "until": until, "start": start, "width": grid.width, "fallback": not near and bool(stocks),
           "scored": near or sorted(paired)}
    near = near or sorted(paired)
    out["near"] = {r: paired[r] for r in near}
    out["rest"] = {r: v for r, v in paired.items() if r not in near}
    out["goals"] = {g: {r: paired[r]} for r, g in (goals or {}).items() if r in paired}
    err = [sum((v[k] - y) ** 2 for rows in out["near"].values() for *v, y in rows) for k in (1, 2)]
    out["tau"] = taus[err[1] < err[0]]          # the noise's time scale: the time constant of whichever replays better
    return out


def _change(b: float | None, a: float | None) -> float | None:
    """The share by which the change lowers a scaled error (negative: raises it); a trifle either way is none."""
    if b is None or a is None:
        return None
    if abs(b - a) <= gt.TRIFLE * 1e-2:
        return 0.0
    return (b - a) / b if b else (0.0 if a == 0 else -1.0)


def bound(se: float, units: float, alpha: float = ALPHA) -> float:
    """The half-width of a confidence sequence for a mean (a normal mixture, Robbins 1970; Howard et al. 2021:
    |S| ≥ √((V + M) log((V + M) / (M a²))), by Ville's inequality), its standard error ``se`` on ``units`` of the record
    it needs. Two-sided at a = 2·``alpha``: by Ville the chance it is ever crossed, either way, however often it is
    looked at, is at most 2·alpha, and each way about alpha when the noise is symmetric. It is a plug-in, asymptotic
    sequence: valid as far as the standard error is (stationary AR(1) noise, read well enough from the record)."""
    v = max(units, 1e-9)
    return se * math.sqrt((v + MIX) / v * math.log((v + MIX) / (MIX * 4 * alpha * alpha)))


def horizon(needs: float) -> float:
    """The most record held out a change the bound cannot decide stays under test for."""
    return max(LONGEST * needs, ob.REFERENCE)


def due(looked: float, needs: float) -> float:
    """When a change under test is looked at next (record held out, s): after the record it needs, then each time
    the record has grown by that or by a quarter, whichever is more (the bound holds however often it looks)."""
    return max(needs, looked + max(needs, looked / 4)) - 1.0      # a second's grace for the clock's rounding


def floor_of(ev: dict) -> float:
    """The least noise correlation from one bucket to the next: what the time constant of what the change touches, in
    whichever of the two replays the record better (``compare``), carries over, while the record held out spans
    fewer than ``SPANS`` of them (a short record reads a slow noise's correlation low, and a day of a day-long
    drain is one draw); none after. What only accumulates (no time constant) keeps whatever it gets wrong: its
    noise, once it drifts, is as slow as can be (``RHO_MAX``), and is also taken as a walk (``pooled``'s
    ``walk``)."""
    tau = ev.get("tau")
    if not tau:
        return RHO_MAX
    return math.exp(-ev["width"] / tau) if ev["until"] - ev["since"] < SPANS * tau else 0.0


def _rho(e: list[float]) -> float:
    """The record's noise correlation from one reading to the next (AR(1)): the larger of what the next reading says
    (its small-record bias taken out: Marriott and Pope 1954) and what one a twelfth of the record on says, so a slow
    drift under fast noise is not missed."""
    n, lag, mean = len(e), max(2, len(e) // 12), sum(e) / len(e)
    e = [v - mean for v in e]
    m2 = sum(v * v for v in e) / n
    if m2 <= 0:
        return 0.0
    r1, rl = (sum(e[i] * e[i + k] for i in range(n - k)) / (n - k) / m2 for k in (1, lag))
    return min(RHO_MAX, max(0.0, r1 + (1 + 3 * r1) / n, max(0.0, rl) ** (1.0 / lag)))


def _effect(rows: list[tuple], least: float = 0.0, walk: bool = False) -> tuple[float, float, float, bool]:
    """One stock's scaled error before and after, and the variance of their difference's mean, given how far the
    two replays are apart: the difference at each reading is δ(δ + 2(after − record)), δ what the change moves the
    replay by, so its noise is the record's own about the better replay (AR(1); its second moment about that replay,
    not its mean, so a bias in the better one counts as noise, never against it), from one bucket to the next at least
    ``least`` once the record says it drifts at all (``DRIFTS``): what the stock's own time constant carries over (its
    process noise drains no faster than the stock), given while the record spans too few of them to read it. With
    ``walk`` (what only accumulates) the noise may be a walk as well, its steps read from the record's successive
    differences: Var = σ²_step Σ_k (Σ_{i≥k} δ_i)², and the larger of the two is taken."""
    n = len(rows)
    b = sum((x - y) ** 2 for _, x, _, y in rows) / n
    a = sum((z - y) ** 2 for _, _, z, y in rows) / n
    e = [y - (x if b <= a else z) for _, x, z, y in rows]
    gap = max(1.0, (rows[-1][0] - rows[0][0]) / max(1, n - 1))
    rho, s2 = _rho(e) ** (1 / gap), sum(v * v for v in e) / n      # per bucket
    rho = max(rho, least) if rho >= DRIFTS else rho    # noise that drifts lasts as the stock does
    acc, run_, last = 0.0, 0.0, rows[0][0]
    for i, x, z, _ in rows:                             # Σ_ij δ_i δ_j ρ^|i−j| (buckets apart), in one pass
        d = x - z
        run_ *= rho ** (i - last)
        acc += d * d + 2 * d * run_
        run_, last = run_ + d, i
    if walk and rho >= DRIFTS and n > 1:                # a walk: its steps from the record, min(i, j) its covariance
        step = sum((e[j + 1] - e[j]) ** 2 for j in range(n - 1)) / max(1, rows[-1][0] - rows[0][0])
        tail, cov = 0.0, 0.0
        for j in range(n - 1, -1, -1):
            tail += rows[j][1] - rows[j][2]
            cov += tail * tail * ((rows[j][0] - rows[j - 1][0]) if j else 1)
        acc = max(acc, step * cov / max(s2, 1e-300))
    return b, a, 4 * s2 * max(acc, 0.0) / (n * n), any(x != z for _, x, z, _ in rows)


def pooled(stocks: dict[str, list], units: float, least: float = 0.0, alpha: float = ALPHA, walk: bool = False) -> dict | None:
    """The change's effect on these stocks' scaled error, with its noise from the record itself: the estimate (the
    share by which it lowers the error) and the bound about it (``lo``, ``hi``, at ``alpha`` each way); None with no
    rows. The stocks' noises may be correlated: their standard errors add (the worst case, Cauchy–Schwarz)."""
    got = [_effect(rows, least, walk) for rows in stocks.values() if rows]
    if not got:
        return None
    k = len(got)
    before, after = sum(g[0] for g in got) / k, sum(g[1] for g in got) / k
    se = sum(math.sqrt(g[2]) for g in got) / k
    scale = before or 1.0
    est = _change(before, after) or 0.0
    h = bound(se, units, alpha) / scale
    return {"before": before, "after": after, "est": est, "lo": est - h, "hi": est + h, "half": h, "se": se / scale,
            "readings": sum(len(r) for r in stocks.values()), "moved": any(g[3] for g in got)}


def slices(ev: dict, spans: list[tuple[float, float]]) -> list[dict]:
    """The evidence as a reader sees it: the scaled error before and after in each window (whole, halves, ...)."""
    out = []
    for lo, hi in spans:
        r = [(x - y, z - y) for rows in ev["near"].values() for i, x, z, y in rows
             if lo <= ev["start"] + (i + 0.5) * ev["width"] < hi]
        if r:
            bb, aa = sum(u * u for u, _ in r) / len(r), sum(v * v for _, v in r) / len(r)
            out.append({"since": lo, "until": hi, "before": bb, "after": aa, "change": _change(bb, aa)})
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


def _more(s: dict, held: float, needs: float, gap: float) -> float:
    """About how much more record the bound needs to narrow to ``gap``, the record going on as it has (its standard
    error falling as one over the root of the record, its mixture's log factor counted)."""
    t = held
    while gap > 0 and t < 100 * horizon(needs) and bound(s["se"] * math.sqrt(held / t), t / max(needs, 1.0)) > gap:
        t *= 1.1
    return t - held if gap > 0 else horizon(needs)


def _says(s: dict) -> str:
    return f"{_pct(s['est'])} (bound {_pct(s['lo'])} to {_pct(s['hi'])}; {s['before']:.3g} → {s['after']:.3g})"


def _harm(s: dict | None, threshold: float) -> bool:
    """Worse beyond the bound's doubt, by the threshold, and by more than the floor."""
    return s is not None and s["hi"] < 0 and s["est"] <= -threshold and s["after"] - s["before"] > FLOOR


def decide(ev: dict, threshold: float, answers: int, new: int, held: float, needs: float,
           simpler: bool = False) -> tuple[str | None, str, float | None]:
    """The verdict (kept, dropped or inconclusive), why, and None; or None, why, and about how much more record (s)
    it needs: keep testing. ``needs``: the least record the change is judged on, the unit the bound counts in."""
    units = held / max(needs, 1.0)
    least = floor_of(ev)
    walk = not ev.get("tau")                              # what only accumulates: its noise may walk
    near = pooled(ev["near"], units, least, walk=walk)
    sc = ev.get("scored") or []
    where = (", ".join(sc[:4]) + (f" and {len(sc) - 4} more" if len(sc) > 4 else "")) or "every stock"
    if near is None:
        if held < GIVE_UP * needs:
            return None, "too few readings of what it touches yet", None
        if answers and not new:
            return "kept", (f"nothing it changes is fitted, so the record cannot judge it; it answers {answers} finding"
                            f"{'s' if answers > 1 else ''} check reported, and makes none"), None
        return "inconclusive", (f"too little record to judge it: no stock it touches has {5} readings both replays "
                                f"follow in {dur(held)} held out; it needs more record"), None
    span = f"over {dur(held)} held out ({near['readings']} readings)"
    near_ = f"near what it touches ({where})"
    worse = [(n, r) for n, r in [("the rest of the model", ev["rest"]), *((f"goal {g}'s stock", r) for g, r in ev["goals"].items())]
             if any(r.values())]
    a_fail = ALPHA / (1 + len(worse))                     # it can fail on any of these: the error split (Bonferroni)
    if _harm(pooled(ev["near"], units, least, a_fail, walk), threshold):
        return "dropped", f"worse {near_}: the scaled error rises by {_says(near)[1:]} {span}", None
    others = [(n, pooled(r, units, least, a_fail, walk)) for n, r in worse]
    for name, s in others:
        if _harm(s, threshold):
            return "dropped", (f"worse elsewhere: {name} by {_says(s)[1:]} {span}, though {near_} it falls by "
                               f"{_says(near)}"), None
    fine = all(s is None or s["est"] > -threshold for _, s in others)
    tiny = abs(near["before"] - near["after"]) + near["half"] * (near["before"] or 1.0) <= FLOOR   # below any noise
    if not near["moved"] and not answers and not simpler and not new:     # the replay is the same with it: no evidence
        if held < horizon(needs):
            return None, "the replay is the same with it on the record so far: it waits for record in which it moves", None
        return "inconclusive", (f"the replay is the same with it on all of {dur(held)} held out {near_}: it needs more "
                                f"record, of a time when what it touches moves"), None
    if near["lo"] > 0 and near["est"] >= threshold and fine and not tiny:
        return "kept", (f"better {near_}: the scaled error falls by {_says(near)} {span} (the threshold is "
                        f"{_pct(threshold)}; a change no better passes so at most {_pct(ALPHA)} of the time), and no "
                        f"worse elsewhere"), None
    if near["lo"] > -threshold and not new and fine:
        if answers:
            return "kept", (f"no worse {near_} (within {_pct(threshold)}: {_says(near)}) {span}, and it answers "
                            f"{answers} finding{'s' if answers > 1 else ''} check reported, making none"), None
        if simpler and not ev.get("fallback"):
            return "kept", (f"simpler, and no worse (within {_pct(threshold)}, {near_}: {_says(near)}, and elsewhere) "
                            f"{span}"), None
    if tiny or (near["hi"] < threshold and near["lo"] > -threshold):     # told apart by less than that, or than the floor
        if new:
            return "dropped", f"no better {near_} ({_says(near)}) {span}, and it makes {new} new finding{'s' if new > 1 else ''}", None
        if held >= GIVE_UP * needs:
            return "inconclusive", (f"the record cannot tell it from the model as it is: within {_pct(threshold)} "
                                    f"{near_}: {_says(near)} {span}; it needs more record, of a time when what it "
                                    f"touches moves"), None
        return None, f"within {_pct(threshold)} so far ({_says(near)})", None
    e = abs(near["est"])
    gap = e if e >= threshold else threshold - e
    more = _more(near, held, needs, gap)
    if held >= horizon(needs):
        return "inconclusive", (f"not yet told from the model as it is: {near_} {_says(near)} {span}; it needs about "
                                f"{dur(more)} more record, as the record has gone"), None
    return None, f"not yet decided: {_says(near)} {span}; it needs about {dur(more)} more record", more


def _event(p, x: dict, what: str, by: str, data: dict) -> None:
    p.events.add(f"model.{what}", item=f"proposal/{x['id']}", source=by, data={"title": x["title"], **data})


JUDGED = ("parameter", "equation", "structure")        # what a replay can judge (a loop's process or gain is not)

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
                                                   "rescoring": False, **({"scorecard": card} if card else {})})
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
                when = due(looked, float(x["hold_out"]))
                if now - since < when or judged >= most:
                    out["waiting"].append({"id": x["id"], "held": now - since, "needs": when})
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
            if stalled and held >= horizon(nd["needs"]):      # the record of what it touches stopped, and stayed so
                why = (f"the record of what it touches stopped {dur(held - (reach - since))} ago, "
                       f"{dur(max(0.0, reach - since))} after it was made; it needs more record")
                pr.event(p, x["id"], "inconclusive", {"verdict": {"verdict": "inconclusive", "why": why, "at": now, "by": by}})
                out["inconclusive"] += 1
                out["verdicts"].append({"id": x["id"], "verdict": "inconclusive", "why": why})
                continue
            if held < due(looked, nd["needs"]) or judged >= most or stalled:
                out["waiting"].append({"id": x["id"], "held": now - since, "needs": due(looked, nd["needs"]),
                                       **({"record": reach - since} if stalled else {})})
                continue
            judged += 1
            ev = compare(p, spec, after, since, now, nd["warm_up"], nd["stocks"], nd["goals"], (nd["tau"], nd["tau_with_it"]))
            results = slices(ev, windows(since, now, pol.windows, min(nd["tau"] or 0.0, nd["needs"] / 2)))
            f = x.get("findings") or {}
            verdict, why, more = decide(ev, pol.threshold, len(f.get("answered") or []), len(f.get("new") or []), held,
                                        nd["needs"], simpler=complexity(after) < complexity(spec))
            q = quiet_held(p, spec, x, since, now) if verdict in ("kept", None) else None
            if q is not None:                                 # it does not vouch for what the record has not exercised
                verdict, why = (None, q) if held < GIVE_UP * nd["needs"] else ("inconclusive", q)
            if verdict is None:
                pr.event(p, x["id"], "testing", {"looked": held, "undecided": why, "more": more,
                                                  **({"not_exercised": q} if q else {})})
                out["waiting"].append({"id": x["id"], "held": held, "needs": due(held, nd["needs"]), "judged": len(results),
                                       "why": why, **({"more": more} if more else {})})
                continue
            state = {"kept": "passed", "dropped": "failed"}.get(verdict, verdict)
            stat = pooled(ev["near"], held / max(nd["needs"], 1.0), floor_of(ev), walk=not ev["tau"])
            pr.event(p, x["id"], state, {"verdict": {"verdict": state, "why": why, "at": now, "threshold": pol.threshold,
                                                      "windows": results, "pooled": stat, "alpha": ALPHA, "held": held,
                                                      "by": by, "warm_up": nd["warm_up"], "tau": nd["tau"],
                                                      "needs": nd["needs"], "scored": nd["stocks"]}})
            out[state] += 1
            out["verdicts"].append({"id": x["id"], "verdict": state, "why": why})
    words = 0
    sets = [y for y in pr.pending(p, spec) if y.get("kind") == REDESIGN]     # a redesign waiting: nothing written over it
    from . import redesign as rd
    from . import reviewer as rv
    if rd.running(p, now, rd.HOLD_FOR):          # a redesign being made: the model it reads held still, for a while
        return out
    first = [y for y in sets if y["state"] == "passed" and pol.accept.get(REDESIGN) == "auto" and not owners(y)][:1]
    held = [y for y in sets if not rv.read_for_owner(spec, y)] if pol.accept.get(REDESIGN) == "auto" else []
    # a redesign the judge may write holds its lines (not one the reviewer left to the owner); one
    # only the owner writes holds nothing (it is carried, or superseded, as the model moves)
    todo = first + [y for y in sorted(pr.pending(p, spec), key=lambda x: x.get("created") or 0) if y not in first]
    for x in todo:                                   # a redesign the owner promoted and the judge passed is written first,
        if x["state"] != "passed" or x.get("kind") not in (*JUDGED, *WORDING, REDESIGN) or pol.accept.get(x.get("kind")) != "auto":
            continue                                 # alone; else one a pass, the oldest first (words as many as passed)
        if owners(x):                                # a removal, a chain rewired, a redesign's control: the owner's
            continue
        if rv.awaiting(spec, x):                     # a reviewed kind: written only after the reviewer's pass
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
    q = ex.quiet(spec, data, least=MIN_WINDOW, readings=12)
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
