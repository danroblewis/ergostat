"""Outside steps as experiments (docs/roadmap/overnight/poor-identifications-proposed.md): a burst's window sized from
the process it identifies, not from y's excursion, and several bursts fitted together, the last held out."""

from __future__ import annotations

import math
import random
import re
import time

import pytest

from ergostat.control import experiments as ex
from ergostat.control import ident

K, THETA, H, KD = 0.2, 20.0, 10.0, 0.5


def burst_loop(seed, n=6000, bursts=((3000, 10.0),), tau=60.0, gain=0.3, width=60, quiet=None, d2=None):
    """``test_churn.burst_loop`` with its numbers open: a loop under integral control (``gain``), its process
    K e^(−θs)/(τs + 1), disturbed by steps nothing measures (v, every 600 s, held still over ``quiet``: from 1000 s
    before each burst to 2000 s after, by default) and by bursts (start, height) through a measured input d (the same
    lag, gain KD). With ``d2``, a second measured input of that many units per burst, the same lag, gain KD too."""
    rnd = random.Random(seed)
    a = math.exp(-1 / tau)
    quiet = quiet if quiet is not None else [(b - 1000, b + 2000) for b, _ in bursts]
    x, xd, u, v = None, 0.0, 25.0, 0.0
    buf, dbuf = [25.0] * int(THETA), [0.0] * int(THETA)
    us, ys, ds, d2s = [], [], [], []
    for k in range(n):
        dk = next((hgt for b, hgt in bursts if b <= k < b + width), 0.0)
        if k % 600 == 0 and not any(lo <= k <= hi for lo, hi in quiet):
            v = rnd.choice([-1, -0.5, 0.5, 1]) * 0.4
        buf.append(u)
        dbuf.append(dk * (1 + (d2 or 0)))
        ud, dd = buf.pop(0), dbuf.pop(0)
        x = K * u if x is None else a * x + (1 - a) * K * ud
        xd = a * xd + (1 - a) * KD * dd
        if k % 10 == 0:
            y = x + xd + v + rnd.gauss(0, 0.01)
            us.append(u)
            ys.append(y)
            ds.append(dk)
            d2s.append(dk * (d2 or 0))
            u += gain * (5.0 - y)
    return (us, ys, ds, d2s) if d2 else (us, ys, ds)


def times(u):
    return [k * H for k in range(len(u))]


def err(r, tau):
    return abs(r.get("K", 0.0) - K) / K + abs((r.get("tau") or 0.0) - tau) / tau


def seconds(text):
    """``8m40s`` -> 520 (``durations.human`` read back)."""
    return sum(float(x) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[u] for x, u in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", text))


def within(r):
    return abs(r["K"] - K) < 0.1 and abs(r["theta"] - THETA) <= 10


def hm(t):
    return time.strftime("%H:%M", time.localtime(t))


SLOW = {"gain": 0.3, "width": 60, "n": 12000}


@pytest.mark.slow
@pytest.mark.xfail(strict=True, reason="not met by any setting in the ranges allowed: see the definition's Where it stopped")
def test_a_slow_process_is_identified_from_its_own_window_not_ys_excursion():
    """Rule 8(ii): τ = 300 s, integral gain 0.3, a burst of 60 s at 3000 s, n = 12000 s, v quiet from 2000 s to the end.
    Every integral gain 0.1-1.0 (by 0.1-0.2), burst width 30, 60 and 120 s and n 12000 and 15000 s was tried: none
    gives a process window on every seed. Where pass 1 is not reached, its fit says "u did not move in the part of the
    record fitted" (``ident.moves``: integral action ramps u, and over the longer window no change passes a twentieth
    of its range). So the claim is not made; the test fails if it ever holds, so the claim can then be made."""
    e0, e1 = [], []
    for seed in range(6):
        u, y, d = burst_loop(seed, n=SLOW["n"], tau=300.0, gain=SLOW["gain"], width=SLOW["width"], quiet=[(2000, SLOW["n"])])
        t = times(u)
        [(k, _)] = ident.outside_steps(d)[:1]
        r0 = ident.around(H, t, u, y, {"d": d}, k)
        r = ex.identify_around(H, t, u, y, {"d": d})
        assert "the part fitted spans less than 5 of τ + θ" in r0["why"]
        assert r["outside_step"]["window"] == "process"
        assert "the part fitted spans less than 5 of τ + θ" not in r["why"]
        assert abs(r["K"] - K) < 0.1
        assert abs(r["theta"] - THETA) <= 10
        e0.append(err(r0, 300.0))
        e1.append(err(r, 300.0))
    assert sum(e1) / 6 < 0.3
    assert sum(e1) / 6 <= 0.5 * sum(e0) / 6


@pytest.mark.slow
def test_a_slow_process_mean_error_from_the_new_path_is_under_half_the_excursions():
    """The part of 8(ii) that holds, on its fixture: over the six seeds the mean of |ΔK|/K + |Δτ|/τ is under 0.3 and at
    most half the excursion's (0.28 against 0.57 when written), though not every seed reaches a process window."""
    e0, e1, process = [], [], 0
    for seed in range(6):
        u, y, d = burst_loop(seed, n=SLOW["n"], tau=300.0, gain=SLOW["gain"], width=SLOW["width"], quiet=[(2000, SLOW["n"])])
        t = times(u)
        [(k, _)] = ident.outside_steps(d)[:1]
        r0 = ident.around(H, t, u, y, {"d": d}, k)
        assert "the part fitted spans less than 5 of τ + θ" in r0["why"]
        r = ex.identify_around(H, t, u, y, {"d": d})
        process += r["outside_step"]["window"] == "process"
        e0.append(err(r0, 300.0))
        e1.append(err(r, 300.0))
    assert process >= 3
    assert sum(e1) / 6 < 0.3
    assert sum(e1) / 6 <= 0.5 * sum(e0) / 6


def test_one_burst_meets_the_churn_bounds_through_the_new_path():
    """Rule 8(i), on ``test_churn``'s own fixture (τ = 60 s)."""
    from .test_churn import burst_loop as churn_loop
    err_loop, err_new = [], []
    for seed in range(6):
        u, y, d = churn_loop(seed)
        t = times(u)
        whole = ident.identify(H, t, u, y, {"d": d})
        r = ex.identify_around(H, t, u, y, {"d": d})
        assert abs(r["K"] - K) < 0.1
        assert abs(r["theta"] - THETA) <= 10
        err_loop.append(err(whole, 60.0))
        err_new.append(err(r, 60.0))
    mean = sum(err_new) / 6
    assert mean < 0.3
    assert mean < sum(err_loop) / 6 / 3


THREE = ((2000, 10.0), (5000, 10.0), (8000, 10.0))


def test_several_outside_steps_are_fitted_together_as_experiments():
    """Rule 8(iii): three equal bursts (the largest is then the first, by bucket order); the joint fit's standard error
    of K is below the largest one's alone on every seed."""
    for seed in range(6):
        u, y, d = burst_loop(seed, n=11000, bursts=THREE)
        t = times(u)
        r = ex.identify_around(H, t, u, y, {"d": d})
        o = r["outside_step"]
        assert r["experiments"] == 3 and len(o["experiments"]) == 3
        assert [s["at"] for s in o["steps"]] == [2000.0, 5000.0, 8000.0]
        assert o["held"] == o["experiments"][2]["since"]
        largest = sorted(ex.steps_of({"d": d}), key=lambda s: (-s["jump"], s["k"]))[0]
        one = ex.around_steps(H, t, u, y, {"d": d}, steps=[largest])
        assert one["outside_step"]["at"] == 2000.0 and one["experiments"] == 1
        assert r["se"]["K"] < one["se"]["K"], seed


def test_steps_whose_windows_overlap_become_one_experiment(monkeypatch):
    """Two bursts 500 s apart (300 s is inside ``POINTS_MIN`` buckets on one input, so one step there), with the windows
    sized from pass 0's process (``PASSES_MAX`` 2 here, so the size is known): one experiment, both steps in it, its
    fitted part ending ⌈S/h⌉ past the later one."""
    u, y, d = burst_loop(0, n=6000, bursts=((2500, 10.0), (3000, 10.0)))
    t = times(u)
    monkeypatch.setattr(ex, "PASSES_MAX", 1)
    p0 = ex.identify_around(H, t, u, y, {"d": d})
    monkeypatch.setattr(ex, "PASSES_MAX", 2)
    r = ex.identify_around(H, t, u, y, {"d": d})
    o = r["outside_step"]
    assert o["window"] == "process" and r["experiments"] == 1
    assert o["experiments"][0]["steps"] == [2500.0, 3000.0]
    c = math.ceil(ex.settling(p0, H) / H)
    assert o["held"] >= 3000.0 + c * H
    assert o["experiments"][0]["since"] == 2500.0 - ident.POINTS_MIN * H and not o["dropped"]


def _second_call(monkeypatch, fake):
    calls = []
    real = ident.identify

    def counted(*a, **kw):
        calls.append(1)
        return fake(*a, **kw) if len(calls) == 2 else real(*a, **kw)
    monkeypatch.setattr(ident, "identify", counted)
    return calls


def test_a_later_pass_that_fails_keeps_the_previous_window(monkeypatch):
    u, y, d = burst_loop(0)
    t = times(u)
    with monkeypatch.context() as m:
        m.setattr(ex, "PASSES_MAX", 1)
        p0 = ex.identify_around(H, t, u, y, {"d": d})
    assert p0["found"] and p0["told_apart"] and p0["form"] == "fopdt"

    _second_call(monkeypatch, lambda *a, **kw: {"found": False, "proposable": False, "told_apart": False, "why": ["fake"]})
    r = ex.identify_around(H, t, u, y, {"d": d})
    o = r["outside_step"]
    assert r["K"] == p0["K"] and o["window"] == "excursion" and o["passes"][1].startswith("not found")
    assert o["passes"][2] == "not run: its windows are pass 1's"     # sized from pass 0's τ, the one kept

    def integrating(h, *a, **kw):
        return {"found": True, "form": "integrating", "K": 0.01, "tau": None, "theta": 20.0, "h": h, "why": [],
                "proposable": True, "told_apart": True, "se": {"K": 1e-9, "theta": 1e-9}}
    _second_call(monkeypatch, integrating)
    r = ex.identify_around(H, t, u, y, {"d": d})
    o = r["outside_step"]
    assert o["window"] == "process" and o["passes"][1] == "kept" and r["form"] == "integrating"
    assert o["passes"][2].startswith("not run: integrating")

    def worse(h, *a, **kw):
        return {"found": True, "form": "fopdt", "K": 0.5, "tau": 60.0, "theta": 20.0, "h": h, "why": ["fake"],
                "proposable": False, "told_apart": False, "se": {}}
    calls = _second_call(monkeypatch, worse)
    r = ex.identify_around(H, t, u, y, {"d": d})
    o = r["outside_step"]
    assert r["K"] == p0["K"] and o["window"] == "excursion"
    assert o["passes"][1] == f"not kept: pass 0 was better ({'proposable' if p0['proposable'] else 'told apart'})"
    assert o["passes"][2] == "not run: its windows are pass 1's" and len(calls) == 2   # pass 2 sized from pass 0, kept


def _covers(lines):
    got = [x for x in lines if "the record after it covers" in x]
    for x in got:
        have, need = re.search(r"covers (\S+) of the (\S+) its process", x).groups()
        assert seconds(have) < seconds(need), x
    return got


def test_a_step_without_enough_record_after_it():
    # (a) one burst 420 s before the end (``outside_steps`` asks for 400 s after a step at least)
    u, y, d = burst_loop(0, n=6000, bursts=((5580, 10.0),))
    t = times(u)
    r = ex.identify_around(H, t, u, y, {"d": d})
    assert not r["proposable"]
    [line] = _covers(r["why"])
    assert line.startswith(f"the step at {hm(5580.0)} (d): the record after it covers 7m of the ")
    assert r["outside_step"]["passes"][1].startswith("not run: no step left")

    # (b) three bursts, the last short (τ = 120 s: its settling then reaches past the end, even with several)
    for tall in (10.0, 20.0):                              # (c): the short one the largest, dropped all the same
        for seed in range(3):
            u, y, d = burst_loop(seed, n=7990, bursts=((2000, 10.0), (4500, 10.0), (7580, tall)), tau=120.0)
            t = times(u)
            r = ex.identify_around(H, t, u, y, {"d": d})
            o = r["outside_step"]
            assert o["window"] == "process" and r["experiments"] == 2, (tall, seed, o["passes"])
            [line] = _covers(o["dropped"])
            assert line.startswith(f"the step at {hm(7580.0)} (d)")
            assert [s["at"] for s in o["steps"]] == [2000.0, 4500.0]
            assert within(r), (tall, seed)

    # (d) three bursts in one experiment, the last two short: once the last is dropped one experiment is left, so its
    # held-out part counts again (b > n), and that makes the second short too
    u, y, d = burst_loop(0, n=7620, bursts=((6300, 10.0), (6800, 10.0), (7210, 10.0)), tau=120.0)
    t = times(u)
    r = ex.identify_around(H, t, u, y, {"d": d})
    o = r["outside_step"]
    assert o["window"] == "process" and r["experiments"] == 1, o["passes"]
    assert [s["at"] for s in o["steps"]] == [6300.0]
    assert len(_covers(o["dropped"])) == 2


def test_a_step_whose_input_has_no_readings_in_its_window_is_dropped():
    u, y, d = burst_loop(0, n=11000, bursts=THREE)
    t = times(u)
    gap = range(500 - 45, 500 + 150)                       # all of the second burst's windows
    d2 = [None if i in gap else 0.0 for i in range(len(u))]
    r = ex.identify_around(H, t, u, y, {"d": d, "d2": d2})
    o = r["outside_step"]
    assert r["experiments"] == 2 and [s["at"] for s in o["steps"]] == [2000.0, 8000.0]
    assert f"the step at {hm(5000.0)}: d2 has no readings in its window" in o["dropped"]

    u1, y1, d1 = burst_loop(0)
    t1 = times(u1)
    gap1 = range(300 - 45, 300 + 150)
    r = ex.identify_around(H, t1, u1, y1, {"d": d1, "d2": [None if i in gap1 else 0.0 for i in range(len(u1))]})
    assert r["found"] is False and r["proposable"] is False
    assert f"the step at {hm(3000.0)}: d2 has no readings in its window" in r["why"]

    uu = [None if i in gap else x for i, x in enumerate(u)]
    r = ex.identify_around(H, t, uu, y, {"d": d})
    assert r["experiments"] == 2 and f"the step at {hm(5000.0)}: u has no readings in its window" in r["outside_step"]["dropped"]


def test_steps_and_passes_are_bounded(monkeypatch):
    heights = [3.0, 9.0, 4.0, 8.0, 5.0, 7.0, 6.0, 10.0, 3.5]
    bursts = tuple((500 + 1000 * i, x) for i, x in enumerate(heights))
    u, y, d = burst_loop(0, n=10000, bursts=bursts)
    t = times(u)
    st = ex.steps_of({"d": d})
    assert len(ident.outside_steps(d)) == 9 and len(st) == ex.STEPS_MAX == 6
    assert [t[s["k"]] for s in st] == [b for b, x in bursts if x >= 5.0]          # the six largest, by bucket
    calls = []
    real = ident.identify
    monkeypatch.setattr(ident, "identify", lambda *a, **kw: calls.append(1) or real(*a, **kw))
    r = ex.identify_around(H, t, u, y, {"d": d})
    assert 1 <= len(calls) <= ex.PASSES_MAX == 3          # pass 0 (the excursion) is one of them
    assert len(r["outside_step"]["steps"]) <= ex.STEPS_MAX


def test_the_reason_names_every_step_and_how_its_window_was_chosen():
    from ergostat.control import proposals as cp
    a, b = 1_700_000_000.0, 1_700_006_300.0
    steps = [{"at": a, "inputs": ["flow.asked"], "jump": 9.0}, {"at": b, "inputs": ["flow.asked"], "jump": 8.0}]
    r = {"K": 0.2, "tau": 100.0, "theta": 20.0,
         "outside_step": {"at": a, "input": "flow.asked", "steps": steps, "window": "process", "passes": ["kept", "kept"],
                          "dropped": []}}
    assert cp._around(r) == f"identified around outside steps at {hm(a)}, {hm(b)} (flow.asked), each window from the " \
                            "process (θ + 4τ = 7m)"
    r["outside_step"].update(window="excursion", passes=["kept", "not found: too little record"])
    assert cp._around(r) == f"identified around outside steps at {hm(a)}, {hm(b)} (flow.asked), each window from y's " \
                            "excursion (not found: too little record)"
    r["outside_step"]["dropped"] = ["the step at 18:00 (flow.asked): the record after it covers 7m of the 8m40s its process "
                                    "needs to settle"]
    assert cp._around(r) == f"identified around outside steps at {hm(a)}, {hm(b)} (flow.asked), each window from y's " \
                            "excursion (not found: too little record); the step at 18:00 (flow.asked): the record after " \
                            "it covers 7m of the 8m40s its process needs to settle"
