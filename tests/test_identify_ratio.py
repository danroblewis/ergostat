"""The HPA's multiplicative rule identified as its own family (numbers/extlaw.py ``_fit_ratio``, SPEC §12d): on records
made by an HPA written here, apart from extlaw, the ratio family is kept and its target recovered; on records made by a
stepper the stepper still is; and too few moves says why."""

from __future__ import annotations

import math
import random

from ergostat.numbers import extlaw as el

SEEDS = range(20)


def hpa(seed: int, n: int = 1200, target: float = 0.6, tolerance: float = 0.1, window: int = 20, lo: int = 3,
        hi: int = 40, scale: float = 1.0, shift: float = 0.0):
    """Load → utilisation → replicas on 15s samples, through the HPA's documented rule: desired ⌈u x / target⌉ outside
    1 ± tolerance, a scale-down to the largest desired of the last ``window`` samples, within [lo, hi]; the load
    swinging (its swing times ``scale``, less ``shift``, not below 0), with noise on it and on the utilisation read."""
    rnd, reps, wants, xs, us = random.Random(seed), 6, [], [], []
    for k in range(n):
        swing = 9 + 7 * math.sin(2 * math.pi * k / 360) + 2 * math.sin(2 * math.pi * k / 83)
        load = max(0.0, scale * swing - shift) + rnd.gauss(0, 0.5)
        util = max(0.01, load / reps + rnd.gauss(0, 0.02))
        r = util / target
        wants = (wants + [math.ceil(reps * r) if abs(r - 1) > tolerance else reps])[-window:]
        reps = min(hi, max(lo, wants[-1] if wants[-1] > reps else min(reps, max(wants))))
        xs.append(util)
        us.append(float(reps))
    return xs, us


def stepper(seed: int, n: int = 1500):
    """The HPA-like stepper of test_extlaw: one more pod past 0.7 for 30s 1m after a move, one fewer under 0.4 for 60s
    5m after one, within [2, 20]."""
    rnd, reps, since, run_up, run_dn, xs, us = random.Random(seed), 4, 10 ** 6, 0, 0, [], []
    for k in range(n):
        load = 3 + 2.5 * math.sin(2 * math.pi * k / 400) + 1.5 * math.sin(2 * math.pi * k / 97) + rnd.gauss(0, 0.3)
        util = max(0.0, load / reps + rnd.gauss(0, 0.03))
        since += 1
        run_up, run_dn = (run_up + 1 if util > 0.7 else 0), (run_dn + 1 if util < 0.4 else 0)
        if reps < 20 and run_up >= 3 and since >= 4:
            reps, since = reps + 1, 0
        elif reps > 2 and run_dn >= 5 and since >= 20:
            reps, since = reps - 1, 0
        xs.append(util)
        us.append(float(reps))
    return xs, us


def test_ratio_identified_on_hpa_record():
    got = []
    for seed in SEEDS:
        best, laws, why = el.fit(*hpa(seed), 15.0)
        got.append((seed, best.family if best else why, best.p.get("target") if best else None))
    ok = [s for s, fam, t in got if fam == "ratio" and abs(t - 0.6) <= 0.06]
    print(f"ratio kept, target within 10%, on {len(ok)} of {len(SEEDS)} seeds", got)
    assert len(ok) >= 18, got


def test_stepper_still_wins_on_stepper_record():
    got = [(seed, (el.fit(*stepper(seed), 15.0)[0] or el.Law("none", {}, 15.0)).family) for seed in SEEDS]
    won = [s for s, fam in got if fam == "stepper"]
    print(f"stepper kept on {len(won)} of {len(SEEDS)} seeds", got)
    assert len(won) >= 18, got


def test_ratio_fits_bounds_and_tolerance_on_saturating_record():
    """A load that swings past both of the HPA's bounds, long enough at each to show them: the fitted law has min 3,
    max 40 and tolerance about 0.1 on every seed, and says them; a record that never reaches 40 has no max, and one that
    never sits at 3 past the window has no min."""
    got = []
    for seed in SEEDS:
        law = el._fit_ratio(*hpa(seed, scale=2.0, shift=8.0), 15.0)
        got.append((seed, law.p["lo"], law.p["hi"], round(law.p["tolerance"], 3), round(law.p["target"], 3)))
    bad = [g for g in got if g[1] != 3 or g[2] != 40 or abs(g[3] - 0.1) > 0.01 or abs(g[4] - 0.6) > 0.006]
    assert not bad, bad
    said = el._fit_ratio(*hpa(0, scale=2.0, shift=8.0), 15.0).said()
    assert "within [3, 40]" in said and "outside 1 ± 0.09" in said, said
    plain = el._fit_ratio(*hpa(0), 15.0)
    assert plain.p["hi"] is None and plain.p["lo"] is None and "within" not in plain.said(), plain.p
    assert 3 < max(hpa(0)[1]) < 40


def test_ratio_needs_moves():
    xs, us = hpa(0)
    ups = [k for k in range(1, len(us)) if us[k] > us[k - 1]]
    assert el._fit_ratio(xs[:ups[el.MIN_MOVES - 1]], us[:ups[el.MIN_MOVES - 1]], 15.0) is None   # two moves up
    assert el._fit_ratio(xs[:ups[el.MIN_MOVES - 1] + 1], us[:ups[el.MIN_MOVES - 1] + 1], 15.0).family == "ratio"
    assert el._fit_ratio(xs, [u + 0.5 for u in us], 15.0) is None          # not a count of replicas
    step = [5.0] * 30 + [6.0] * 30                                         # one move: no law fits, and why says so
    best, laws, why = el.fit([0.7] * 60, step, 15.0)
    assert best is None and laws == [] and "too few moves of its output" in why, why


def test_an_identified_ratio_law_is_said_and_drawn_as_a_declared_one_marked_identified(tmp_path):
    from tests.test_known_laws import HPA, blocks, hpa_node
    best, laws, _ = el.fit(*hpa(0), 15.0)
    assert best.family == "ratio" and set(best.se) == {"target", "tolerance"} and best.se["target"] > 0
    said = best.said()
    assert said.startswith("ratio (the HPA's rule): u ← ⌈u·x / 0.6") and "± " in said and "down after 5m" in said, said
    assert best.short() == f"⌈u x / {best.p['target']:.3g}⌉"
    n = hpa_node(blocks(tmp_path, "", {"laws": {"hpa": best.as_dict()}}))
    declared = hpa_node(blocks(tmp_path, HPA))
    assert n["identified"] and "declared" not in n and n["fn"]["kind"] == "identified ratio", n
    assert n["fn"]["law"] == best.short() and n["fn"]["sketch"] == declared["fn"]["sketch"] == "saturation", n
    assert ["identified", said] in n["rows"] and said in n["says"]
