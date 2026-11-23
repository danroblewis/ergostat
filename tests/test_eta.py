"""Each item's completion estimate (SPEC §5a, *Completion estimates*; numbers/survival.py, etamodel.py, eta.py,
tests/eta_backtest.py): Kaplan–Meier with censoring, residual life given age, the path's expected visits, capacity, dependencies,
rework, an M/M/c queue against Erlang C, the owner's case, a lease's age, the what-if, the backtest, and the seed."""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

import pytest

from ergostat import precedence as pr
from ergostat.numbers import eta, etacheck
from ergostat.numbers.etamodel import Attempt, BlockIn, Inputs, ItemAt, KindIn, _unscheduled, fundamental, read
from ergostat.numbers.survival import KM

from .eta_backtest import backtest
from .eta_synthetic import GATED_BATCH, gated_record, generate, project
from .test_take_order import GATED, PAUSED
from .test_take_order import project as take_project

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
    # older than every stay seen, none censored: the tail (the longest tenth's mean excess, else every stay's mean)
    assert km.quantile(0.5, age=60) == pytest.approx(30 * math.log(2))
    assert km.mean_residual(60) == pytest.approx(30, rel=0.05)


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
    b = BlockIn("dev", "t", ["todo"], pool, list(shared), False, 99, attempts=atts, run=KM([a.dur for a in atts]))
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


def test_a_workspace_pool_is_held_from_its_take_until_the_item_finishes():
    # 12 items, the dev pool 6, but a workspace pool of 3 taken at dev and held through review (a stay, no block):
    # never more than 3 items between their take and their finish, and what waits for one holds nothing
    inp = inputs(n=12, pool=6, review=(1200.0,) * 10)
    inp.blocks[0].workspace, inp.workspaces = "code", {"code": 3}
    for r in range(10):
        run = eta._Run(inp, eta.Flags(arrivals=False), random.Random(r), {}, {}, True)
        run.go(eta.HORIZON)
        spans = [(run.start[i], run.finish[i]) for i in inp.items]
        for t, _ in spans:
            assert sum(1 for a, z in spans if a <= t < z) <= 3, (r, t)
    plain = eta.simulate(inputs(n=12, pool=6, review=(1200.0,) * 10), runs=20)["kinds"]["t"]["p50"] - T0
    held = eta.simulate(inp, runs=20)["kinds"]["t"]["p50"] - T0
    assert held == pytest.approx(4 * (600 + 1200), rel=0.05) and plain == pytest.approx(2 * 600 + 1200, rel=0.05)
    inp.items["t/0"].holds = {"code"}
    inp.items["t/1"].holds = {"code"}
    inp.items["t/2"].holds = {"code"}
    assert "it waits for one, holding nothing" in eta.reasons(inp)["t/5"]["why"]


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
    past = inputs(n=1, pool=1, durs=(100.0, 200.0))                      # held past every run, its TTL 600 s:
    past.blocks[0].ttl = 600.0
    past.items["t/0"].lease = ("dev", T0 - 550)
    run = eta._Run(past, eta.Flags(), random.Random(2), {}, {}, False)
    a = run.attempt(0, 550.0)
    assert a.how in ("expired", "ack") and 0 < a.dur <= 50.0              # never at once, never past its TTL
    assert sum(run.attempt(0, 550.0).how == "expired" for _ in range(200)) > 100


def test_whatif_pool_and_failure_change_the_estimates():
    inp = inputs(n=24, pool=2)
    base = eta.simulate(inp, runs=20)["kinds"]["t"]["p50"] - T0
    assert eta.simulate(inp, runs=20, pools={"dev": 6})["kinds"]["t"]["p50"] - T0 == pytest.approx(base / 3, rel=0.05)
    assert eta.simulate(inp, runs=20, failures={"dev": 0.5})["kinds"]["t"]["p50"] - T0 > base * 1.5
    held = inputs(n=8, pool=4)                                            # a pool lowered under the leases held:
    for i in range(4):
        held.items[f"t/{i}"].lease = ("dev", T0 - 10)
    g = eta.simulate(held, runs=20, pools={"dev": 1}, failures={"dev": 0.5})
    assert g["capacity"]["dev"] == 4 and g["limit"]["dev"] == 1          # their lanes kept until they end, none new
    starts = sorted(s[1] for segs in g["schedule"].values() for s in segs if s[3] == "dev")
    assert all(t >= T0 for t in starts) and len([t for t in starts if t == T0]) == 4
    assert eta.simulate(held, runs=0)["items"] == {}                     # no run: not worked out, never "beyond"
    few = eta.simulate(held, runs=5)
    assert all(x["p90"] is None and x["runs"] == 5 for x in few["items"].values())
    why = eta.reasons(inp)
    assert why["t/5"]["why"].startswith("0 of 2 busy in dev; 5 ahead of it") and why["t/5"]["position"] == 6


# ---- from a record


def owners_record(tmp_path, seed: int = 0):
    """A day at 2 tickets an hour (the history), then 100 brought in at once; the dev pool is 6."""
    p = project(tmp_path, pool=6)
    generate(p, T0, 24, rate=2, pool=6, backlog=0, fail=0.1, rework=0.1, seed=3 + seed, prefix="h", stop_arrivals=20)
    generate(p, T0 + 86400, 30, rate=0, pool=6, backlog=100, fail=0.1, rework=0.1, seed=4 + seed, prefix="b")
    return p


def test_the_owners_case_100_tickets_6_leases(tmp_path):
    p = owners_record(tmp_path)
    at = T0 + 86400 + 60
    inp = read(p, p.model.spec, ["ticket"], at)
    assert sum(1 for i in inp.items if i.startswith("ticket/b")) == 100
    assert not any(x.unscheduled for x in inp.items.values())        # (each can move: the run is as it was)
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
    # three truths of the owner's case, each cut 15 min, 2 h and 4 h after the batch: the p90 covers about 90%, the
    # estimates' mean is not biased (a small share of the error), and the median path is far worse
    got = {"all": [], "path": []}
    for seed in range(3):
        (tmp_path / str(seed)).mkdir()
        p = owners_record(tmp_path / str(seed), seed)
        cuts = [T0 + 86400 + h * 3600 for h in (0.25, 2, 4)]
        res = backtest(p, p.model.spec, ["ticket"], cuts, {"path": eta.ABLATIONS["path"], "all": eta.Flags()}, runs=60,
                       budget=6)
        for k in got:
            got[k].append(res[k])
            assert res[k]["unresolved"] == 0
    mean = lambda k, f: sum(r[f] for r in got[k]) / 3                 # noqa: E731
    assert sum(r["items"] for r in got["all"]) >= 700
    assert 0.85 <= mean("all", "coverage") <= 1.0                     # about 90% finish before their p90
    assert abs(mean("all", "bias")) < 0.25 * mean("all", "mae")        # unbiased: the estimate's mean against what happened
    assert 0.3 <= mean("all", "p50") <= 0.7
    assert mean("path", "coverage") < 0.6                             # a median path with no pool: the owner's 17:43
    assert mean("all", "mae") < mean("path", "mae") * 0.6


# ---- a gate under the pool (etamodel.MIN_RUN, etamodel._measured)


BATCH = T0 + GATED_BATCH                                 # the gated record's batch brought in


def old_model(monkeypatch):
    """The model before refusals and measured concurrency: every give-back a run, the pool the capacity."""
    from ergostat.numbers import etamodel
    monkeypatch.setattr(etamodel, "MIN_RUN", 0.0)
    monkeypatch.setattr(etamodel, "MEASURED", 0.0)


def test_uncounted_refusals_are_not_runs(tmp_path, monkeypatch):
    p = gated_record(tmp_path)
    at = BATCH + 900
    dev = next(b for b in read(p, p.model.spec, ["ticket"], at).blocks if b.name == "dev")
    assert not any(a.how == "nack" and not a.counted and a.dur < 30 for a in dev.attempts)
    assert len(dev.refusals) > len(dev.attempts) and set(dev.refusals) == {300.0}      # most takes refused
    assert dev.run.quantile(0.5) == pytest.approx(3 * 3600, rel=0.15)                  # a run: about 3 h
    why = eta.reasons(read(p, p.model.spec, ["ticket"], at))
    waiting = next(x["why"] for i, x in why.items() if x["waits_in"] == "dev" and x["position"])
    assert "of its takes refused (its gate closed), each put off about 5m" in waiting
    old_model(monkeypatch)                                       # before: each refusal a run of 2 s
    old = next(b for b in read(p, p.model.spec, ["ticket"], at).blocks if b.name == "dev")
    assert not old.refusals and old.run.quantile(0.5) < 30


def test_measured_concurrency_caps_a_gated_block(tmp_path, monkeypatch):
    from ergostat.numbers import etamodel
    p = gated_record(tmp_path)
    at = BATCH + 900
    caps = etamodel.capacities(p, {"at": at})
    assert caps["dev"]["lanes"] == 4 and caps["merge"]["lanes"] == 1
    said = "4 at once while items waited (the record, p90), under its pool of 20"
    assert caps["dev"]["source"] == said and caps["merge"]["source"] == "its pool"     # (merge's pool binds: 1)
    inp = read(p, p.model.spec, ["ticket"], at)
    dev = next(b for b in inp.blocks if b.name == "dev")
    assert dev.capacity() == 4 and dev.capacity({"dev": 20}) == 20                     # (the what-if overrides it)
    assert any(f"busy in dev ({said})" in x["why"] for x in eta.reasons(inp).values())
    for r in range(5):                                   # the simulation: never more than 4 runs at once
        run = eta._Run(inp, eta.Flags(), random.Random(r), {}, {}, True)
        run.go(eta.HORIZON)
        spans = [(s[1], s[2]) for segs in run.segs.values() for s in segs if s[3] == "dev"]
        assert max(sum(1 for a, z in spans if a <= t < z) for t, _ in spans) <= 4, r
    g = eta.simulate(inp, runs=40)                       # the owner's picture: the simulated Timeline's first hour
    first = [s[1] for segs in g["schedule"].values() for s in segs if s[3] == "dev" and s[1] < at + 3600]
    assert g["limit"]["dev"] == 4 and 0 < len(first) <= 4
    (tmp_path / "o").mkdir()                             # an ungated pool of 6: its pool stands, no measure said
    assert not etamodel.capacities(owners_record(tmp_path / "o"), {"at": T0 + 86400 + 900})["dev"]["measured"]
    old_model(monkeypatch)
    assert etamodel.capacities(p, {"at": at})["dev"]["lanes"] == 20


def test_backtest_gated_record_improves(tmp_path, monkeypatch):
    # the gated record's three truths, cut 15 min, 2 h and 4 h after the batch: the p50's error falls by a third at least
    got: dict[str, list] = {"new": [], "old": []}
    for seed in range(3):
        p = gated_record(tmp_path / str(seed), seed)
        cuts = [BATCH + h * 3600 for h in (0.25, 2, 4)]
        got["new"].append(backtest(p, p.model.spec, ["ticket"], cuts, {"all": eta.Flags()}, runs=60, budget=6)["all"])
        with monkeypatch.context() as m:
            old_model(m)
            got["old"].append(backtest(p, p.model.spec, ["ticket"], cuts, {"all": eta.Flags()}, runs=60, budget=6)["all"])
    mean = lambda k, f: sum(r[f] for r in got[k]) / 3                 # noqa: E731
    table = {k: [(r["items"], r["unresolved"], round(r["mae"]), round(r["bias"]), round(r["p50"], 2), round(r["coverage"], 2))
                 for r in v] for k, v in got.items()}
    assert mean("new", "mae") <= mean("old", "mae") * 2 / 3, table
    assert mean("new", "coverage") >= 0.8, table
    assert all(r["unresolved"] == 0 for v in got.values() for r in v), table
    # the records with no gate: the same inputs as before (no refusal, the pool measured as it is), so the same estimates
    (tmp_path / "o").mkdir()
    (tmp_path / "s").mkdir()
    steady = project(tmp_path / "s", pool=3)
    generate(steady, T0, 48, rate=6, pool=3, seed=7)
    for p, at in ((owners_record(tmp_path / "o"), T0 + 86400 + 900), (steady, T0 + 16 * 3600)):
        new = read(p, p.model.spec, ["ticket"], at)
        with monkeypatch.context() as m:
            old_model(m)
            old = read(p, p.model.spec, ["ticket"], at)
        assert [(b.capacity(), [a.dur for a in b.attempts]) for b in new.blocks] == \
            [(b.capacity(), [a.dur for a in b.attempts]) for b in old.blocks] and not any(b.refusals for b in new.blocks)


# ---- the calibration the Timeline says (etacheck.py, from the eta worker)


def test_calibration_of_last_weeks_estimates_on_the_owners_record(tmp_path):
    # now 1.75 days after the batch's first 15 minutes: the week's last cut lands there, the three before the record
    p = owners_record(tmp_path)
    now = T0 + 86400 + 900 + 1.75 * 86400
    assert etacheck.cuts(now)[-1] == T0 + 86400 + 900
    cal = etacheck.calibration(p, p.model.spec, ["ticket"], now)["ticket"]
    assert cal["items"] >= 100 and 0.8 <= cal["coverage"] <= 1.0, cal
    assert cal["mae"] > 0 and cal["since"] == now - etacheck.WEEK
    assert "finished by their p90" in cal["said"] and f"({cal['items']} tickets)" in cal["said"]
    from ergostat.web.eta_api import merge
    est = {"at": now, "runs": 1, "kinds": {}, "capacity": {}, "schedule": {}, "items": {"ticket/x": {}},
           "calibration": {"ticket": cal}}
    assert merge({"items": []}, est)["eta"]["calibration"]["ticket"] == cal
    worse = etacheck.said("ticket", {"items": 41, "coverage": 0.79})   # rounded down: never said better than it was
    assert worse == "last week's estimates: 7 in 10 tickets finished by their p90 (41 tickets)"


def test_calibration_with_three_finished_says_too_few(tmp_path):
    p = project(tmp_path, pool=3)
    generate(p, T0, 10, rate=0, pool=3, backlog=3, fail=0.0, rework=0.0, seed=2)
    now = T0 + 600 + 1.75 * 86400                                        # the last cut 10 minutes in
    cal = etacheck.calibration(p, p.model.spec, ["ticket"], now)["ticket"]
    assert cal["items"] <= 3
    assert cal["said"] == "tickets: too few finished last week to check"


def test_calibration_counts_an_item_open_at_every_cut_once(monkeypatch):
    # three items open at all four cuts, each finished an hour after the last: 3 items, not 12 judgements, so too few
    now = T0 + 2 * 86400
    at = etacheck.cuts(now)

    def three(p, spec, kinds, t, truth=False):
        inp = inputs(n=3, pool=3, at=t)
        inp.finished_at = {i: at[-1] + 3600 for i in inp.items}
        return inp
    monkeypatch.setattr(etacheck, "read", three)
    monkeypatch.setattr(eta, "simulate", lambda inp, *a, **k: {"runs": 5, "items": {
        i: {"p50": inp.at + 600, "p90": inp.at + 1200 if inp.at < at[-1] else at[-1] + 7200, "mean": inp.at + 700}
        for i in inp.items}})

    class P:
        class events:
            query = staticmethod(lambda **k: [{"time": now}])
    cal = etacheck.calibration(P, None, ["t"], now)["t"]
    assert cal["items"] == 3 and cal["coverage"] == 1.0                    # each by its latest cut: by its p90
    assert cal["said"] == "ts: too few finished last week to check"
    every = etacheck.score([three(None, None, None, t) for t in at], now)["kinds"]["t"]
    assert every["items"] == 12 and every["coverage"] == 0.25             # (the backtest's: each estimate judged)


def test_calibration_is_worked_out_by_the_worker_never_on_a_request(tmp_path, monkeypatch):
    # the calibration held up in the worker: the estimates come first, a request is not slowed, and once it is
    # worked out it is given beside them; asked again within the hour, it is not worked out again
    import threading
    import time
    from collections import OrderedDict

    from ergostat.web import eta_api
    for name in ("_CACHE", "_WANT", "_CAL", "_CAL_WANT"):
        monkeypatch.setattr(eta_api, name, OrderedDict())
    p = project(tmp_path, pool=3)
    generate(p, time.time() - 3 * 3600, 3, rate=4, pool=3, backlog=10, seed=5)
    held, calls = threading.Event(), []

    def slow(p_, spec, kinds, now):
        calls.append(now)
        held.wait(30)
        return {"ticket": {"coverage": 0.5, "items": 20, "mae": 60.0, "since": now - etacheck.WEEK, "said": "said"}}
    monkeypatch.setattr(etacheck, "calibration", slow)
    try:
        first = eta_api.estimates(p, p.model, wait=30)
        assert first and first["items"] and "calibration" not in first     # the estimates, not held up by it
        deadline = time.monotonic() + 10
        while not calls and time.monotonic() < deadline:
            time.sleep(0.02)
        assert calls                                                          # begun, and held
        t = time.monotonic()
        again = eta_api.estimates(p, p.model)
        assert time.monotonic() - t < 0.5 and "calibration" not in again
    finally:
        held.set()
    deadline = time.monotonic() + 10
    while "calibration" not in (eta_api.estimates(p, p.model) or {}) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert eta_api.estimates(p, p.model)["calibration"]["ticket"]["coverage"] == 0.5
    assert len(calls) == 1


# ---- what cannot move is not scheduled; a failure is said


def test_an_open_run_on_an_item_moved_on_by_its_own_events(tmp_path):
    p, evs = project(tmp_path), []
    for n in range(6):                                    # five runs ended; the sixth's item moved on with it open
        i, t = f"ticket/{n}", T0 + n * 100
        evs += [{"at": t, "type": "ticket.opened", "item": i},
                {"at": t + 1, "type": "ergostat.lease.taken", "item": i, "data": {"item": i, "run": f"r{n}", "block": "dev"}},
                {"at": t + 50, "type": "ticket.implemented", "item": i}]
        if n < 5:
            evs.append({"at": t + 51, "type": "ergostat.lease.ended", "item": i,
                        "data": {"item": i, "run": f"r{n}", "how": "ack", "state": "review"}})
    p.events.add_many(evs)
    inp = read(p, p.model.spec, ["ticket"], T0 + 1000)    # (was: KeyError: 'how')
    dev = next(b for b in inp.blocks if b.name == "dev")
    assert len(dev.attempts) == 5 and dev.run.n - dev.run.events == 1   # the open run: going (censored)
    assert inp.items["ticket/5"].state == "review" and inp.items["ticket/5"].lease is None


def paused_inputs(n=20):
    inp = inputs(n=n, pool=2)
    k = inp.kinds["t"]
    k.states.insert(1, "parked")
    k.paused, k.arrivals, k.arrive_at = {"parked"}, 6.0, [("todo", 1.0)]
    k.km["parked"] = KM([60.0])
    inp.items["t/0"].state = "parked"
    return inp


def test_paused_item_does_not_hold_the_run():
    inp = paused_inputs()
    _unscheduled(inp)
    t = time.monotonic()
    g = eta.simulate(inp, runs=200)
    assert g["runs"] == 200 and time.monotonic() - t < 1.0      # (was: every run to the 90-day horizon)
    assert g["kinds"]["t"]["p50"] is not None and g["kinds"]["t"]["unscheduled"] == 1
    assert g["items"]["t/0"] == {"unscheduled": True, "why": "paused in parked", "p50": None, "p90": None,
                                 "mean": None, "start": None, "dead": 0.0, "runs": 200}
    assert g["items"]["t/1"]["p50"] is not None and "t/0" not in g["schedule"]


def test_an_item_paused_partway_through_a_run_does_not_hold_it():
    inp = paused_inputs()
    b = inp.blocks[0]                                     # a third of the runs leave the item parked
    b.attempts = [Attempt(600.0, "ack", "done")] * 2 + [Attempt(600.0, "ack", "parked")]
    inp.items["t/9"].preds = ["t/1"]
    inp.items["t/0"].lease = ("dev", T0 - 10)             # a paused item holding a lease: run, its slot held
    _unscheduled(inp)
    assert not inp.items["t/0"].unscheduled
    t = time.monotonic()
    g = eta.simulate(inp, runs=200)
    assert g["runs"] == 200 and time.monotonic() - t < 1.0      # (was: a run to the horizon whenever one parks)
    assert g["kinds"]["t"]["p50"] is not None                   # (was: inf, the counted out in the kind's last)
    outs = [x for x in g["items"].values() if x.get("out")]
    assert outs and all(x["why"].startswith("counted out in ") and x["p50"] is not None for x in outs)
    run = eta._Run(inp, eta.Flags(), random.Random(3), {}, {}, False)
    run.go(eta.HORIZON)
    assert run.open == 0 and run.gone and "t/0" in run.start
    assert ("t/1" not in run.gone) or "t/9" in run.gone         # waiting on one parked: counted out with it


def test_waiting_on_a_paused_item_is_unscheduled(tmp_path):
    inp = paused_inputs()
    inp.items["t/1"].preds, inp.items["t/2"].preds = ["t/0"], ["t/1"]
    _unscheduled(inp)
    assert inp.items["t/1"].unscheduled == "waits on t/0, which is parked"
    assert inp.items["t/2"].unscheduled == "waits on t/1, which waits on t/0, which is parked"
    assert not inp.items["t/3"].unscheduled
    assert eta.simulate(inp, runs=20)["kinds"]["t"]["unscheduled"] == 3
    nofin = inputs(n=2)
    nofin.kinds["t"].finished = set()
    _unscheduled(nofin)
    assert nofin.items["t/0"].unscheduled == "has no finished state (t)"
    p = take_project(tmp_path, PAUSED)                    # from the record: read marks them
    ev, t = p.events, time.time() - 600
    ev.add("ticket.opened", item="ticket/a", at=t)
    ev.add("ticket.held", item="ticket/a", at=t + 1)
    ev.add("ticket.opened", item="ticket/b", data={"blocked_by": "ticket/a"}, at=t + 2)
    got = read(p, p.model.spec, ["ticket"], time.time()).items
    assert got["ticket/a"].unscheduled == "paused in held"
    assert got["ticket/b"].unscheduled == "waits on ticket/a, which is held"


def test_off_block_items_unscheduled(tmp_path, monkeypatch):
    from collections import OrderedDict

    from ergostat.web import eta_api
    p = take_project(tmp_path, GATED)
    p.events.add("ticket.opened", item="ticket/a", at=time.time() - 60)
    inp = read(p, p.model.spec, ["ticket"], time.time())
    assert inp.items["ticket/a"].unscheduled == "waits for dev, switched off"
    x = eta.simulate(inp, runs=20)["items"]["ticket/a"]
    assert x["unscheduled"] and x["p50"] is None and x["why"] == "waits for dev, switched off"
    monkeypatch.setattr(eta_api, "_CACHE", OrderedDict())     # the Items list: reasons' words kept, after the cause
    why = eta_api.estimates(p, p.model, wait=10.0)["items"]["ticket/a"]["why"]
    assert why.startswith("not scheduled: waits for dev, switched off; waits for dev, which is switched off now (by")
    on = inputs(n=2)                                      # one block of two off: the other takes it
    on.blocks.append(BlockIn("dev2", "t", ["todo"], 1, [], False, 9, off="gate", attempts=on.blocks[0].attempts,
                             run=on.blocks[0].run))
    _unscheduled(on)
    assert not on.items["t/0"].unscheduled
    on.blocks[0].off = "gate"
    _unscheduled(on)
    assert on.items["t/0"].unscheduled == "waits for dev and dev2, switched off"


def test_a_failed_simulation_is_said(tmp_path, monkeypatch):
    from collections import OrderedDict

    from ergostat.web import eta_api
    p = take_project(tmp_path)
    p.events.add("ticket.opened", item="ticket/a", at=time.time() - 60)

    def boom(*a, **k):
        raise KeyError("how")
    monkeypatch.setattr(eta, "simulate", boom)
    monkeypatch.setattr(eta_api, "_CACHE", OrderedDict())     # (none kept past the test under a reused id)
    est = eta_api.estimates(p, p.model, wait=10.0)
    assert est["error"] == "KeyError: 'how'"                  # kept, not None (was: a silent unlevelled Timeline)
    got = eta_api.merge({"items": [{"id": "ticket/a"}], "edges": []}, est)
    assert got["eta"] is None and got["eta_error"] == "KeyError: 'how'"
    assert eta_api.merge({"items": []}, None)["eta_error"] is None
    js = (Path(eta_api.__file__).parent / "static" / "relations.js").read_text()
    assert "the simulation failed: ${d.eta_error}" in js and "the simulation is being worked out" in js
