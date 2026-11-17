"""What a system dynamics modeller's review of the tools asked for (SPEC §12b, §12c): a total that a frozen
stock never raises, loop dominance per stock with ties and unscored loops said, a what-if that is typed in
its units and refused when the model cannot run it, calibration within a parameter's range, the whole model
said for what it is, joint sensitivity draws, delays rescaled per sample, and extreme conditions one input
and one parameter at a time."""

from __future__ import annotations

import math
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.numbers import dominance as dm
from ergostat.numbers import estimate as es
from ergostat.numbers import extremes
from ergostat.numbers import fit as ft
from ergostat.numbers import observe as ob
from ergostat.numbers import proposals as pr
from ergostat.numbers import sensitivity as sens
from ergostat.numbers import simulate as sim
from ergostat.store import Project

from .test_numbers import QUEUE, queue_project, write


def found(spec, code="extreme-conditions"):
    out = []
    extremes.findings(spec, lambda c, msg, where, about: out.append((c, msg, about)))
    return [x for x in out if x[0] == code]


# ---- the total: a frozen stock counts, never drops out

def test_a_stock_frozen_by_a_value_never_raises_the_total():
    moving = [10.0 + (i % 5) for i in range(30)]
    good = ft.stats([v + 0.3 * ((i * 7) % 3 - 1) for i, v in enumerate(moving)], moving)
    still = ft.stats([12.0] * 30, moving)
    assert still["r2"] == 0.0 and still["still"]
    both = ft.total({"stock.a": good, "stock.b": good})
    frozen = ft.total({"stock.a": good, "stock.b": still})
    assert frozen["r2"] < both["r2"] and frozen["nmse"] > both["nmse"] and frozen["stocks"] == 2


def test_a_what_ifs_fit_leads_with_the_payoff_and_is_shown_before_anything_is_stored(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    got = pr.whatif_fit(p, {"k": "3"}, snap)
    assert got["fit_after"]["total"]["nmse"] < got["fit_before"]["total"]["nmse"]
    assert got["touched"] == ["flow.served", "stock.queue"] and not got["refused"]
    worse = pr.whatif_fit(p, {"k": "300"}, snap)                                  # drains it almost at once: worse, never better
    assert worse["fit_after"]["total"]["nmse"] > worse["fit_before"]["total"]["nmse"]
    assert worse["fit_after"]["total"]["r2"] <= worse["fit_before"]["total"]["r2"]
    assert not pr.stored(p)


# ---- a value typed: in its unit, a time above 0

def _prm(**kw):
    from ergostat.spec.ir import Parameter
    return Parameter(**{"name": "x", **kw})


def test_a_duration_needs_its_unit_and_a_time_is_above_zero():
    t = _prm(value=19.2 / 3600, duration=True)
    with pytest.raises(pr.ProposalError, match="write it with its unit"):
        pr.parse_value(t, "20")
    assert pr.parse_value(t, "20s") == pytest.approx(20 / 3600) and pr.parse_value(t, "2m") == pytest.approx(2 / 60)
    for bad in ("0s", "-5s", "−5s"):
        with pytest.raises(pr.ProposalError, match="more than 0"):
            pr.parse_value(t, bad)
    assert pr.parse_value(_prm(value=0.1, duration=True, range=(-1.0, 1.0)), "-5s") == pytest.approx(-5 / 3600)
    rate = _prm(value=2.0, unit="1/h")
    assert pr.parse_value(rate, "-5") == -5 and pr.parse_value(rate, "1e-3") == 0.001
    with pytest.raises(pr.ProposalError, match="not a time"):
        pr.parse_value(rate, "20s")
    with pytest.raises(pr.ProposalError, match="not a number"):
        pr.parse_value(rate, "five")


# ---- a what-if the model cannot run is said, and never proposed

SCALED = QUEUE.replace("equation: k * stock.queue", "equation: k * stock.queue / scale").replace(
    "parameters:\n", "parameters:\n  scale:\n    value: 1\n    range: [0.5, 2]\n")


def test_a_what_if_that_divides_by_zero_is_drawn_as_faulty_and_refused_as_a_proposal(tmp_path):
    from ergostat.web.numbers_api import post
    from ergostat.web.server import Live, api
    p, snap = queue_project(tmp_path, text=SCALED)
    live = Live(p)
    got = api(live, "series", {"since": ["1h"], "refs": ["stock.queue"], "strip": ["1"], "replay": ["1"], "whatif": ["scale:0"]})
    assert any("flow.served divides by 0" in x for x in got["whatif_invalid"])
    fit = pr.whatif_fit(p, {"scale": "0"}, snap)
    assert fit["refused"] and "divides by 0" in fit["refused"][0]
    code, x = post(live, "propose", 3600.0, {"whatif": ["scale:0"]})
    assert code == 409 and "divides by 0" in x["error"] and not pr.stored(p)
    code, x = post(live, "propose", 3600.0, {"whatif": ["scale:3"]})                # outside its range: proposed, and said
    assert code == 200 and "outside its range" in x["reason"] and x["warnings"]


def test_values_tried_together_are_one_proposal_and_an_accepted_one_is_never_overwritten(tmp_path):
    p, snap = queue_project(tmp_path, text=SCALED)
    x = pr.propose_values(p, {"k": "3", "scale": "1.5"}, snap)
    assert x["parameters"] == {"k": 3.0, "scale": 1.5} and "together" in x["reason"]
    assert x["target"] == "parameter.k, parameter.scale" and "scale: 1 → 1.5" in x["title"]
    with pytest.raises(pr.ProposalError, match="already"):
        pr.propose_values(p, {"k": "2"}, snap)                                          # what is written
    one = pr.propose_value(p, "k", "3", snap)
    pr.accept(p, one["id"], snap)
    back = pr.propose_value(p, "k", "2", snap)
    pr.accept(p, back["id"], snap)
    again = pr.propose_value(p, "k", "3", snap)                                         # 3 again: a new proposal
    assert again["id"] != one["id"] and again["status"] == "pending"
    assert pr.stored(p)[one["id"]]["status"] == "accepted"


# ---- calibration: within the parameter's range, said when it runs to an end of it

def test_calibration_keeps_to_the_range_and_says_when_the_record_wants_more(tmp_path):
    text = QUEUE.replace("    estimate: true\n", "    estimate: true\n    range: [1, 2.5]\n")
    p, snap = queue_project(tmp_path, k_true=3.0, text=text)
    e = es.estimate(p, snap)["k"]
    assert e["value"] <= 2.5 + 1e-9 and e["at_range"] == "high"
    why = es.judged(e, 2.0)
    assert "high end of its range" in why and "Widen the range" in why
    free = es.estimate(*queue_project(tmp_path, k_true=3.0))["k"]
    assert free["value"] == pytest.approx(3.0, rel=0.05) and not free["at_range"]


def test_the_whole_model_with_a_decision_in_a_loop_is_said_for_what_it_is(tmp_path):
    text = QUEUE.replace("flows:\n", "flows:\n  extra:\n    from: queue\n", 1) + textwrap.dedent("""\
    goals:
      short:
        stock: queue
        hold: "<= 5"
    blocks:
      decide:
        type: program
        run: "true"
        in: [goal.short.error]
        out: flow.extra
    """)
    spec, _ = sp.read(write(tmp_path, text))
    assert es.open_loops(spec) and es.scope_words(spec, "whole") == es.OPEN_WORDS
    assert es.scopes(spec, ["k"], "whole")[0].label == es.OPEN_WORDS
    spec, _ = sp.read(write(tmp_path, QUEUE))
    assert not es.open_loops(spec) and es.scope_words(spec, "whole") == "the whole model"
    assert es.label("k@up", {"parameter": "k", "scope": "system:up"}) == "k (system up alone)"


# ---- sensitivity: joint draws, tails only from enough runs, delays rescaled per sample

def test_parameters_estimated_together_are_drawn_jointly():
    unc = [{"name": "a", "how": "estimate", "value": 2.0, "se": 0.1, "sd": 0.1, "logged": True, "corr": {"b": 0.9}},
           {"name": "b", "how": "estimate", "value": 5.0, "se": 0.2, "sd": 0.2, "logged": True, "corr": {"a": 0.9}}]
    d = sens.draws(unc, 200)
    la, lb = [math.log(x["a"] / 2) for x in d], [math.log(x["b"] / 5) for x in d]
    ma, mb = sum(la) / 200, sum(lb) / 200
    r = sum((x - ma) * (y - mb) for x, y in zip(la, lb, strict=True)) / math.sqrt(
        sum((x - ma) ** 2 for x in la) * sum((y - mb) ** 2 for y in lb))
    assert r == pytest.approx(0.9, abs=0.05)
    indep = sens.draws([{**u, "corr": {}} for u in unc], 200)
    la = [math.log(x["a"] / 2) for x in indep]
    lb = [math.log(x["b"] / 5) for x in indep]
    assert abs(sum(x * y for x, y in zip(la, lb, strict=True))) / 200 / (0.1 * 0.2) < 0.2


def test_an_estimate_far_from_the_value_written_widens_its_spread():
    spec, _ = sp.read(write_tmp(QUEUE))
    near = sens.uncertain(spec, {"k": {"value": 2.0, "se": 0.05, "logged": True}})[0]
    far = sens.uncertain(spec, {"k": {"value": 3.0, "se": 0.05, "logged": True}})[0]
    assert near["sd"] == pytest.approx(0.05) and far["sd"] == pytest.approx(math.hypot(0.05, math.log(1.5)))
    assert far["low"] < 2 < 3 < far["high"]


def write_tmp(text):
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    return write(d, text)


def test_the_tails_are_drawn_only_from_enough_runs(tmp_path):
    text = QUEUE.replace("    estimate: true\n", "    estimate: true\n    range: [1, 3]\n")
    p, snap = queue_project(tmp_path, text=text)
    data = ob.measured(p, ob.Grid(snap["at"] - 7200, snap["at"], 60))
    few = sens.fan(p.model.spec, data, 1800, 10, k=40)["bands"]["stock.queue"]
    many = sens.fan(p.model.spec, data, 1800, 10)["bands"]["stock.queue"]
    assert "p5" not in few and "p25" in few and "p5" in many and sens.SAMPLES >= 100


DELAYED = """\
name: d
parameters:
  lag:
    value: 1h
    range: [30m, 2h]
stocks:
  pipe:
    unit: jobs
    sensor:
      manual: true
flows:
  in:
    to: pipe
    sensor:
      manual: true
  out:
    from: pipe
    driven-by: +flow.in
    equation: DELAY3(flow.in, lag)
"""


def test_a_samples_delay_starts_in_its_own_steady_state(tmp_path):
    write(tmp_path, DELAYED)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(241):
        t = now - 7200 + i * 30
        p.measurements.add("sensor/in.main", 10.0, at=t)
        p.measurements.add("sensor/pipe.main", 10.0, at=t)
    data = ob.measured(p, ob.Grid(now - 7200, now, 60))
    band = sens.fan(p.model.spec, data, 1800, 10)["bands"].get("flow.out")
    assert band is None or max(b - a for a, b in zip(band["p5"], band["p95"], strict=True)) < 1e-6   # 10 in, 10 out, whatever its lag


# ---- extreme conditions: each input and each parameter alone, named

def test_an_input_at_zero_in_a_denominator_is_found_and_named(tmp_path):
    text = QUEUE.replace("equation: k * stock.queue", "equation: stock.queue / auxiliary.staff").replace(
        "    driven-by: +stock.queue\n", "    driven-by: [+stock.queue, -auxiliary.staff]\n") + textwrap.dedent("""\
    auxiliaries:
      staff:
        unit: people
        exogenous: true
        sensor:
          manual: true
    """)
    spec, probs = sp.read(write(tmp_path, text))
    got = found(spec)
    assert got and any("auxiliary.staff at 0" in m and "divides by 0" in m for _, m, _ in got), got


def test_a_parameter_at_the_end_of_its_range_is_pushed_and_named(tmp_path):
    text = QUEUE + "  spill:\n    from: queue\n    driven-by: +stock.queue\n    equation: stock.queue * (1 - share)\n"
    text = text.replace("parameters:\n", "parameters:\n  share:\n    value: 0.5\n    range: [0, 2]\n")
    spec, probs = sp.read(write(tmp_path, text))
    assert not [x for x in probs if x.level == "error"], [str(x) for x in probs if x.level == "error"]
    msgs = [m for _, m, _ in found(spec)]
    assert any("parameter share at 2" in m and "negative rate" in m for m in msgs), msgs


# ---- loop dominance: per stock, ties and unscored loops said

TWO_SMOOTHED = """\
name: s
parameters:
  t: 1h
stocks:
  a:
    unit: x
    sensor:
      manual: true
  b:
    unit: x
    sensor:
      manual: true
auxiliaries:
  goal-a:
    unit: x
    exogenous: true
    sensor:
      manual: true
  goal-b:
    unit: x
    exogenous: true
    sensor:
      manual: true
flows:
  move-a:
    to: a
    two-way: true
    driven-by: [+auxiliary.goal-a, -stock.a]
    equation: (auxiliary.goal-a - stock.a) / t
  move-b:
    to: b
    two-way: true
    driven-by: [+auxiliary.goal-b, -stock.b]
    equation: (auxiliary.goal-b - stock.b) / t
"""


def test_loops_of_stocks_that_do_not_interact_are_never_weighed_against_each_other(tmp_path):
    write(tmp_path, TWO_SMOOTHED)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    a = b = 0.0
    for i in range(121):
        t = now - 3600 + i * 30
        ga, gb = 10 + 3 * math.sin(i / 9), 5 + 2 * math.cos(i / 13)
        for ref, v in (("a", a), ("b", b), ("goal-a", ga), ("goal-b", gb)):
            p.measurements.add(f"sensor/{ref}.main", v, at=t)
        a += (ga - a) * 30 / 3600
        b += (gb - b) * 30 / 3600
    data = ob.measured(p, ob.Grid(now - 3600, now, 30))
    got = dm.dominance(p.model.spec, data)
    assert set(got["stocks"]) == {"stock.a", "stock.b"} and got["integration_steps"] > 30
    for s in ("stock.a", "stock.b"):
        x = got["stocks"][s]
        vals = [v for v in next(iter(x["relative"].values())) if v is not None]
        assert vals and all(v == pytest.approx(-1.0) for v in vals)                  # alone at its stock: all of its feedback
        assert x["named"] and list(x["share"].values()) == [1.0]


def test_tied_loops_name_no_dominant_one(tmp_path):
    text = GROWTH_TIED
    write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(61):
        p.measurements.add("sensor/people.main", 100 * math.exp(-(i - 60) / 60), at=now - 3600 + i * 60)
    data = ob.measured(p, ob.Grid(now - 3600, now, 20))
    x = dm.dominance(p.model.spec, data)["stocks"]["stock.people"]
    assert x["ties"] > 0 and not any(x["dominant"]) and all(v == 0 for v in x["share"].values())


GROWTH_TIED = """\
name: g
parameters:
  k: 1
stocks:
  people:
    unit: people
    sensor:
      manual: true
flows:
  deaths:
    from: people
    driven-by: +stock.people
    equation: k * stock.people
  leaving:
    from: people
    driven-by: +stock.people
    equation: k * stock.people
"""


def test_a_stock_with_an_unscored_loop_names_no_dominant_loop_and_says_how_many_are_scored(tmp_path):
    text = QUEUE.replace("flows:\n", "flows:\n  extra:\n    from: queue\n", 1) + textwrap.dedent("""\
    goals:
      short:
        stock: queue
        hold: "<= 5"
    blocks:
      decide:
        type: program
        run: "true"
        in: [goal.short.error, +flow.arrivals]
        out: flow.extra
    """)
    write(tmp_path, text)
    p, _ = queue_project(tmp_path, text=text)
    data = ob.measured(p, ob.Grid(time.time() - 3600, time.time(), 30))
    got = dm.dominance(p.model.spec, data)
    x = got["stocks"]["stock.queue"]
    assert not x["named"] and len(x["scored"]) < len(x["loops"]) and not any(x["dominant"])
    assert all(v is None for v in x["share"].values())


def test_a_single_link_the_run_has_no_value_for_is_said_to_be_assumed(tmp_path):
    text = QUEUE.replace("flows:\n", "flows:\n  extra:\n    from: queue\n", 1) + textwrap.dedent("""\
    goals:
      short:
        stock: queue
        hold: "<= 5"
    blocks:
      decide:
        type: program
        run: "true"
        in: [goal.short.error]
        out: flow.extra
    """)
    write(tmp_path, text)
    p, _ = queue_project(tmp_path, text=text)
    data = ob.measured(p, ob.Grid(time.time() - 3600, time.time(), 30))
    got = dm.dominance(p.model.spec, data)
    through = [k for k, v in got["assumed"].items() if v]
    assert through and any("goal.short" in a for k in through for a in got["assumed"][k])


def test_a_replay_records_its_steps_only_when_asked(tmp_path):
    p, snap = queue_project(tmp_path)
    data = ob.measured(p, ob.Grid(snap["at"] - 3600, snap["at"], 20))
    assert not sim.replay(p.model.spec, data).trace
    run = sim.replay(p.model.spec, data, trace={"stock.queue", "flow.served"})
    assert len(run.trace) >= 20 * sim.SUBSTEPS and set(run.trace[5][1]) == {"stock.queue", "flow.served"}
