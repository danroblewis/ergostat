"""Each item's completion estimate (SPEC §5a, *Completion estimates*; numbers/survival.py, etamodel.py, eta.py,
tests/eta_backtest.py): Kaplan–Meier with censoring, residual life given age, the path's expected visits, capacity, dependencies,
rework, an M/M/c queue against Erlang C, the owner's case, a lease's age, the what-if, the backtest, and the seed."""

from __future__ import annotations

import math
import random

import pytest

from ergostat import precedence as pr
from ergostat.numbers import eta
from ergostat.numbers.etamodel import Attempt, BlockIn, Inputs, ItemAt, KindIn, fundamental, read
from ergostat.numbers.survival import KM

from .eta_backtest import backtest
from .eta_synthetic import generate, project

T0 = 1_790_000_000.0


# ---- survival


def test_kaplan_meier_with_censoring():
    # Gehan's 6-MP arm (Freireich et al. 1963), the textbook table: remission weeks, + censored
    ended = [6, 6, 6, 7, 10, 13, 16, 22, 23]
    going = [6, 9, 10, 11, 17, 19, 20, 25, 32, 32, 34, 35]
    km = KM(ended, going)
    for t, s in ((6, 0.857), (7, 0.807), (10, 0.753), (13, 0.690), (16, 0.627), (22, 0.538), (23, 0.448)):
        assert km.S(t) == pytest.approx(s, abs=0.001), t
    assert km.S(5.9) == 1.0
    assert km.S(9) == km.S(7)                                 # a stay still going at 9 ends nothing there
    naive = KM(ended)                                         # the censored left out: far too short
    assert naive.S(16) < 0.3 < km.S(16)


def test_residual_life_is_conditioned_on_age():
    km = KM([10, 20, 30, 40, 50])
    assert km.quantile(0.5) == 30
    assert km.quantile(0.5, age=25) == 15                     # S(25) = 0.6: half of it is 0.3, first reached at 40
    assert km.quantile(0.5, age=45) == 5                      # (an old item: only the longest stays are left)
    assert km.mean_residual(25) < km.mean_residual(0)
    tail = KM([100.0] * 5, [400.0] * 5)                       # half still going past every end: an exponential tail
    assert tail.quantile(0.9, age=400) > 0 and tail.S(1000) < tail.S(400)
    rnd = random.Random(1)
    assert all(km.sample(rnd, 25) <= 25 for _ in range(200))


def test_fundamental_matrix_counts_rework_visits():
    # a → b; b → a half the time (rework), else done: each visited twice on average
    v = fundamental(["a", "b", "done"], {"a": [("b", 1.0)], "b": [("a", 0.5), ("done", 0.5)]}, {"done"})
    assert v == pytest.approx({"a": 2.0, "b": 2.0})


# ---- the simulation, on inputs made here


def inputs(n=20, pool=2, durs=(600.0,), fail=0.0, at=T0, review=None, shared=()) -> Inputs:
    """``n`` items queued in ``todo``, a block taking them (``pool``, runs of ``durs``, ``fail`` of them given back),
    then ``review`` (a stay, no block) or done."""
    states = ["todo", "review", "done"] if review else ["todo", "done"]
    nxt = {"todo": [("review" if review else "done", 1.0)]}
    ended = {}
    if review:
        nxt["review"] = [("done", 1.0)]
        ended["review"] = list(review)
    k = KindIn("t", states, {"done"}, nxt, ended, {s: KM(ended.get(s) or [60.0]) for s in states}, {})
    atts = [Attempt(d, "ack", "review" if review else "done") for d in durs]
    k_fail = round(fail * 100)
    atts = atts * (100 - k_fail) + [Attempt(d, "nack", None, 0.0, True) for d in durs] * k_fail
    b = BlockIn("dev", "t", ["todo"], pool, list(shared), False, 99, atts, KM([a.dur for a in atts]))
    items = {f"t/{i}": ItemAt(f"t/{i}", "t", "todo", at - 1000 + i, at - 1000 + i) for i in range(n)}
    return Inputs(at, {"t": k}, [b], items)


def test_capacity_is_never_exceeded():
    inp = inputs(n=30, pool=3, durs=(300.0, 600.0, 900.0), fail=0.2)
    run = eta._Run(inp, eta.Flags(), random.Random(5), {}, {}, True)
    run.go(eta.HORIZON)
    spans = [(s[1], s[2], s[4]) for segs in run.segs.values() for s in segs if s[3] == "dev"]
    assert len(spans) >= 30
    for t in sorted({a for a, _, _ in spans}):
        on = [lane for a, z, lane in spans if a <= t < z]
        assert len(on) <= 3 and len(set(on)) == len(on), t          # at most its pool, one run a lane
    assert {lane for *_, lane in spans} == {0, 1, 2}
    seats = inputs(n=30, pool=6, shared=[("agent:ai", 2)])          # the agent's seats bind before the pool
    g = eta.simulate(seats, runs=20)
    assert g["capacity"]["dev"] == 2
    assert g["kinds"]["t"]["p50"] - T0 == pytest.approx(30 / 2 * 600, rel=0.05)


def test_dependencies_are_respected():
    inp = inputs(n=6, pool=6)
    inp.items["t/0"].preds = ["t/1"]
    inp.items["t/1"].preds = ["t/2"]
    inp.items["t/2"].level, inp.items["t/1"].level = 2, 1
    for r in range(20):
        run = eta._Run(inp, eta.Flags(), random.Random(r), {}, {}, False)
        run.go(eta.HORIZON)
        assert run.start["t/1"] >= run.finish["t/2"] and run.start["t/0"] >= run.finish["t/1"]
    g = eta.simulate(inp, runs=20)
    assert g["items"]["t/0"]["p50"] == pytest.approx(T0 + 3 * 600)


def test_rework_adds_time():
    plain = eta.simulate(inputs(n=20, pool=2), runs=50)
    failing = eta.simulate(inputs(n=20, pool=2, fail=0.3), runs=50)
    assert failing["kinds"]["t"]["p50"] - T0 > (plain["kinds"]["t"]["p50"] - T0) * 1.3
    tried = eta.simulate(inputs(n=20, pool=2), runs=50, failures={"dev": 0.3})   # the what-if, the same
    assert tried["kinds"]["t"]["p50"] - T0 == pytest.approx(failing["kinds"]["t"]["p50"] - T0, rel=0.15)


def erlang_c(c: int, lam: float, mu: float) -> float:
    a = lam / mu
    top = a ** c / math.factorial(c) * (c / (c - a))
    p_wait = top / (sum(a ** k / math.factorial(k) for k in range(c)) + top)
    return p_wait / (c * mu - lam)


def test_mmc_wait_matches_erlang_c():
    # c = 3 servers, runs exponential (mean 1 h), Poisson arrivals at 2.4 an hour (ρ = 0.8): Wq = Erlang C
    rnd = random.Random(11)
    c, lam, mu, n = 3, 2.4 / 3600, 1 / 3600, 6000
    inp = inputs(n=n, pool=c, durs=tuple(rnd.expovariate(mu) for _ in range(4000)))
    t = T0
    for i in range(n):                                        # each item comes due (put off until) at its arrival
        t += rnd.expovariate(lam)
        inp.items[f"t/{i}"].not_before = t
    waits = []
    for r in range(3):
        run = eta._Run(inp, eta.Flags(arrivals=False), random.Random(r), {}, {}, False)
        run.go(1e9)
        waits += [run.start[i] - inp.items[i].not_before for i in list(inp.items)[500:]]   # past the warm-up
    assert sum(waits) / len(waits) == pytest.approx(erlang_c(c, lam, mu), rel=0.12)


def test_the_same_seed_gives_the_same_estimates():
    inp = inputs(n=15, pool=2, durs=(100.0, 500.0, 900.0), fail=0.2)
    a, b = eta.simulate(inp, runs=30, seed=4), eta.simulate(inp, runs=30, seed=4)
    assert a["items"] == b["items"] and a["schedule"] == b["schedule"]
    assert eta.simulate(inp, runs=30, seed=5)["items"] != a["items"]


def test_a_leased_item_is_conditioned_on_its_lease_age():
    inp = inputs(n=2, pool=2, durs=tuple(float(x) for x in range(100, 1001, 50)))
    inp.items["t/0"].lease = ("dev", T0 - 900)                # held 900 s: only the longest runs are left
    inp.items["t/1"].lease = ("dev", T0)                      # just taken
    g = eta.simulate(inp, runs=100)
    assert g["items"]["t/0"]["p90"] - T0 <= 110
    assert g["items"]["t/1"]["p50"] - T0 > 400
    why = eta.reasons(inp)
    assert why["t/0"]["waits_in"] == "dev" and "running in dev for 15m" in why["t/0"]["why"]


def test_whatif_pool_and_failure_change_the_estimates():
    inp = inputs(n=24, pool=2)
    base = eta.simulate(inp, runs=20)["kinds"]["t"]["p50"] - T0
    assert eta.simulate(inp, runs=20, pools={"dev": 6})["kinds"]["t"]["p50"] - T0 == pytest.approx(base / 3, rel=0.05)
    assert eta.simulate(inp, runs=20, failures={"dev": 0.5})["kinds"]["t"]["p50"] - T0 > base * 1.5
    why = eta.reasons(inp)
    assert why["t/5"]["why"].startswith("0 of 2 busy in dev; 5 ahead of it") and why["t/5"]["position"] == 6


# ---- from a record


def owners_record(tmp_path):
    """A day at 2 tickets an hour (the history), then 100 brought in at once; the dev pool is 6."""
    p = project(tmp_path, pool=6)
    generate(p, T0, 24, rate=2, pool=6, backlog=0, fail=0.1, rework=0.1, seed=3, prefix="h")
    generate(p, T0 + 86400, 30, rate=0, pool=6, backlog=100, fail=0.1, rework=0.1, seed=4, prefix="b")
    return p


def test_the_owners_case_100_tickets_6_leases(tmp_path):
    p = owners_record(tmp_path)
    at = T0 + 86400 + 60
    inp = read(p, p.model.spec, ["ticket"], at)
    assert sum(1 for i in inp.items if i.startswith("ticket/b")) == 100
    g = eta.simulate(inp, runs=60)
    # each ticket's dev work, its runs' mean (median 20 min, σ 0.6) over the runs it needs (failed 1 in 10, sent back
    # by review 1 in 10), six at once: 100 / 6 × that, and the review and merge of the last after it
    runs = 1 / 0.9 / 0.9
    expect = 100 / 6 * 1200 * math.exp(0.18) * runs
    last = g["kinds"]["ticket"]["p50"] - at
    assert 0.85 * expect < last < 1.35 * expect, (last / 3600, expect / 3600)
    cpm = pr.build(p.events, p.model.spec, ["ticket"], at, at - 3600)       # the projection before: no pool
    assert cpm["end"] - at < expect / 4
    ends = sorted(g["items"][i]["p50"] for i in inp.items)
    assert ends[10] - at < ends[-10] - at - 4 * 3600          # staggered by the pool, not all at once


def test_backtest_p90_coverage_on_a_synthetic_record(tmp_path):
    p = owners_record(tmp_path)
    cuts = [T0 + 86400 + h * 3600 for h in (0.25, 2, 4)]
    got = backtest(p, p.model.spec, ["ticket"], cuts, {"path": eta.ABLATIONS["path"], "all": eta.Flags()},
                           runs=60, budget=6)
    assert got["all"]["items"] >= 250
    assert 0.8 <= got["all"]["coverage"] <= 1.0               # about 90% finish before their p90 (one realisation: correlated)
    assert got["path"]["coverage"] < 0.6                      # a median path with no pool: the owner's 17:43
    assert got["all"]["mae"] < got["path"]["mae"] * 0.75
