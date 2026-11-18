"""The tools system dynamics uses to improve and use a model (SPEC §12b, §12c): calibration of the
whole model and of each system alone, Monte Carlo sensitivity (a fan on the projection), what-if
(nothing kept unless proposed and accepted), extreme-conditions tests (check findings) and loop
dominance (Loops That Matter)."""

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
from ergostat.numbers import observe as ob
from ergostat.numbers import proposals as pr
from ergostat.numbers import sensitivity as sens
from ergostat.numbers import simulate as sim
from ergostat.numbers import version as ver
from ergostat.store import Project

from .test_numbers import QUEUE, queue_project, write


def read(tmp_path, text):
    return sp.read(write(tmp_path, text))


def found(spec, code):
    out = []
    extremes.findings(spec, lambda c, msg, where, about: out.append((c, msg, about)))
    return [x for x in out if x[0] == code]


# ---- a parameter's range: what it might be

def test_a_range_is_read_checked_and_versioned_only_where_written(tmp_path):
    spec, probs = read(tmp_path, QUEUE)
    plain = ver.version(spec)
    spec, probs = read(tmp_path, QUEUE.replace("    estimate: true\n", "    estimate: true\n    range: [1, 4]\n"))
    assert not [p for p in probs if p.level == "error"] and spec.parameters["k"].range == (1.0, 4.0)
    assert ver.version(spec) != plain and ver.structure(spec) == ver.structure(read(tmp_path, QUEUE)[0])
    _, probs = read(tmp_path, QUEUE.replace("    estimate: true\n", "    estimate: true\n    range: [4, 1]\n"))
    assert any(p.code == "bad-range" for p in probs)
    _, probs = read(tmp_path, QUEUE.replace("    estimate: true\n", "    estimate: true\n    range: [3, 4]\n"))
    assert any(p.code == "parameter-range" for p in probs)                  # 2 is outside [3, 4]
    spec, _ = read(tmp_path, QUEUE.replace("    value: 2          # what we believe\n    unit: 1/h\n",
                                           "    value: 30m\n    range: [10m, 1h]\n"))
    assert spec.parameters["k"].range == pytest.approx((1 / 6, 1.0))         # durations, in hours


# ---- sensitivity: a Latin hypercube, and a fan on the projection

def test_latin_hypercube_draws_use_each_stratum_once_and_are_the_same_each_time():
    unc = [{"name": "a", "how": "range", "low": 0.0, "high": 10.0},
           {"name": "b", "how": "estimate", "value": 2.0, "se": 0.1, "logged": True}]
    d = sens.draws(unc, 20)
    assert d == sens.draws(unc, 20) and len(d) == 20
    assert sorted(int(x["a"] // 0.5) for x in d) == list(range(20))         # one in each twentieth of the range
    assert all(x["b"] > 0 for x in d) and abs(sum(math.log(x["b"] / 2) for x in d) / 20) < 0.05


def test_the_fan_spreads_around_the_projection_over_what_the_model_says_is_uncertain(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0, text=QUEUE.replace("    value: 2 ", "    value: 3 ").replace(
        "    estimate: true\n", "    estimate: true\n    range: [2, 4]\n"))
    data = ob.measured(p, ob.Grid(snap["at"] - 7200, snap["at"], 120))
    run = sim.replay(p.model.spec, data)
    proj = sim.project(p.model.spec, data, run, 1800, points=30)
    f = sens.fan(p.model.spec, data, 1800, 30)
    band = f["bands"]["flow.served"]
    assert f["samples"] == sens.SAMPLES and f["parameters"][0]["how"] == "range"
    end = proj.values["flow.served"][-1]
    assert band["p5"][-1] < band["p25"][-1] <= end <= band["p75"][-1] < band["p95"][-1]
    assert band["p95"][0] - band["p5"][0] > 0.2 * end                           # the drain is k · queue: k from 2 to 4
    none = sens.fan(read(tmp_path, QUEUE)[0], data, 1800, 30)                  # no range, no estimate: nothing to sample
    assert none["samples"] == 0 and none["bands"] == {}


def test_an_estimates_standard_error_is_sampled_where_no_range_is_written(tmp_path):
    p, snap = queue_project(tmp_path)
    es.estimate(p, snap)
    unc = sens.uncertain(p.model.spec, es.load(p, p.model.spec))
    assert unc and unc[0]["how"] == "estimate" and unc[0]["low"] < 2 < unc[0]["high"]


# ---- what-if: tried on the page, kept only as a proposal the owner accepts

def test_a_what_if_moves_the_projection_and_changes_nothing_until_proposed_and_accepted(tmp_path):
    from ergostat.web.server import Live, api
    p, snap = queue_project(tmp_path, k_true=3.0)
    live = Live(p)
    q = {"since": ["1h"], "refs": ["stock.queue"], "strip": ["1"], "replay": ["1"]}
    text = (tmp_path / "ergostat.yaml").read_text()
    base = {x["ref"]: x for x in api(live, "series", q)["series"]}
    got = api(live, "series", {**q, "whatif": ["k:4"]})
    tried = {x["ref"]: x for x in got["series"]}
    assert got["whatif"] == [{"name": "k", "value": 4.0, "was": 2.0, "unit": "1/h", "duration": False}]
    assert tried["stock.queue"]["whatif_projection"][-1] < base["stock.queue"]["projection"][-1]   # drains faster
    assert tried["stock.queue"]["projection"] == base["stock.queue"]["projection"]                 # the model's own, as it was
    assert api(live, "series", {**q, "whatif": ["nope:1"]})["whatif_error"]
    assert (tmp_path / "ergostat.yaml").read_text() == text and not pr.pending(p)
    from ergostat.web.numbers_api import post
    code, x = post(live, "propose", 3600.0, {"parameter": ["k"], "value": ["3"]})
    assert code == 200 and x["scope"] == "what-if" and x["status"] == "pending"
    assert x["fit_after"]["total"]["r2"] >= x["fit_before"]["total"]["r2"]
    assert (tmp_path / "ergostat.yaml").read_text() == text                                         # proposed, not applied
    assert post(live, "propose", 3600.0, {"parameter": ["k"], "value": ["three"]})[0] == 409
    code, done = post(live, f"proposals/{x['id']}/accept", 3600.0)
    assert code == 200 and "value: 3 " in (tmp_path / "ergostat.yaml").read_text()


# ---- calibration: each part alone, each system alone, the whole model

TWO = """\
name: two
systems:
  upstream: {}
  downstream: {}
parameters:
  a:
    value: 1
    unit: 1/h
    estimate: true
    system: upstream
  b:
    value: 1
    unit: 1/h
    estimate: true
    system: downstream
stocks:
  first:
    unit: jobs
    system: upstream
    sensor:
      manual: true
  second:
    unit: jobs
    system: downstream
    sensor:
      manual: true
flows:
  arrivals:
    to: first
    system: upstream
    sensor:
      manual: true
  handed-on:
    from: first
    to: second
    system: upstream
    driven-by: +stock.first
    equation: a * stock.first
    sensor:
      manual: true
  done:
    from: second
    system: downstream
    driven-by: +stock.second
    equation: b * stock.second
"""


def two_project(tmp_path, a=3.0, b=1.5, minutes=300):
    write(tmp_path, TWO)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    x = y = 0.0
    for i in range(minutes * 2 + 1):
        t = now - minutes * 60 + i * 30
        r = 10 + 6 * ((i // 25) % 2)
        p.measurements.add("sensor/first.main", x, at=t)
        p.measurements.add("sensor/second.main", y, at=t)
        p.measurements.add("sensor/arrivals.main", r, at=t)
        p.measurements.add("sensor/handed-on.main", a * x, at=t)
        for _ in range(30):
            h = a * x
            x += (r - h) / 3600
            y += (h - b * y) / 3600
    return p, {"at": now, "window": minutes * 60.0, "starts": now - minutes * 60}


def test_calibration_scopes_say_what_each_fits_and_integrates(tmp_path):
    spec, _ = read(tmp_path, TWO)
    parts = es.scopes(spec, ["a", "b"], "parts")
    assert [s.names for s in parts] == [["a", "b"]]                      # they share the stock second: fitted together
    systems = es.scopes(spec, ["a", "b"], "systems")
    assert [(s.key, s.names, sorted(s.integrate)) for s in systems] == [
        ("system:downstream", ["b"], ["second"]), ("system:upstream", ["a"], ["first"])]
    whole = es.scopes(spec, ["a", "b"], "whole")
    assert whole[0].names == ["a", "b"] and sorted(whole[0].integrate) == ["first", "second"]
    with pytest.raises(ValueError):
        es.scopes(spec, ["a"], "everything")


@pytest.mark.parametrize("which", ["systems", "whole"])
def test_each_calibration_recovers_the_parameters_and_proposes_them_with_the_fit_before_and_after(tmp_path, which):
    p, snap = two_project(tmp_path)
    got = es.estimate(p, snap, which=which)
    vals = {e["parameter"]: e["value"] for e in got.values()}
    assert vals["a"] == pytest.approx(3.0, rel=0.05) and vals["b"] == pytest.approx(1.5, rel=0.05)
    if which == "systems":
        assert set(got) == {"a@upstream", "b@downstream"} and got["b@downstream"]["fitted_to"] == ["stock.second"]
    made = pr.make(p, snap, which=which)
    mine = [x for x in made if x.get("scope", "").startswith("system:" if which == "systems" else "whole")]
    assert mine and all(x["fit_after"]["total"]["r2"] >= x["fit_before"]["total"]["r2"] for x in mine)
    assert all(("calibrated on" in x["reason"]) for x in mine)
    assert es.path(p, ver.structure(p.model.spec), which).exists()


def test_a_proposal_made_stale_by_another_accepted_is_no_longer_offered(tmp_path):
    p, snap = two_project(tmp_path)
    parts = pr.make(p, snap)
    whole = pr.make(p, snap, which="whole")
    assert {x["scope"] for x in pr.pending(p)} >= {"parts", "whole"}       # one calibration keeps the other's
    pr.accept(p, parts[0]["id"], snap)
    assert not [x for x in pr.pending(p) if x["id"] == whole[0]["id"]]
    with pytest.raises(pr.ProposalError):
        pr.accept(p, whole[0]["id"], snap)


# ---- extreme conditions: the model's own equations pushed to the extreme

def test_an_outflow_that_takes_what_is_not_there_is_found_by_the_extreme_conditions_test(tmp_path):
    bad = QUEUE.replace("equation: k * stock.queue", "equation: k * 5")
    spec, probs = read(tmp_path, bad)
    got = found(spec, "extreme-conditions")
    assert got and got[0][2] == "stock.queue" and "falls below empty" in got[0][1]
    assert "extreme-conditions" in {x.code for x in probs}                      # ergostat check says it
    spec, _ = read(tmp_path, QUEUE)
    assert not found(spec, "extreme-conditions")                               # first-order: it stops when empty


def test_the_extreme_conditions_test_runs_only_where_findings_are_shown(tmp_path, monkeypatch):
    """It runs the model many times over (seconds on a large model): loading the model, as every command
    and the run do, never runs it; the findings (check, the Check page, the model tools) do, once."""
    from ergostat import model as mdl
    bad = QUEUE.replace("equation: k * stock.queue", "equation: k * 5")
    write(tmp_path, bad)
    runs = []
    real = extremes.findings
    monkeypatch.setattr(extremes, "findings", lambda spec, say: (runs.append(1), real(spec, say)))
    m = mdl.load(tmp_path)
    assert not runs and not mdl.check(m, warnings=False) and not runs     # loaded, and checked for errors: not run
    assert any("extreme-conditions" == x.code for x in m.problems) and runs == [1]
    assert any("falls below empty" in msg for lv, msg in mdl.check(m) if lv == "warn") and runs == [1]   # once
    assert [x.code for x in m.problems] == [x.code for x in sp.read(tmp_path / "ergostat.yaml")[1]]   # as check finds them


def test_a_one_way_flow_running_backwards_and_a_division_by_zero_are_found(tmp_path):
    text = QUEUE + """\
  spill:
    from: queue
    driven-by: [+stock.queue, +stock.other]
    equation: stock.queue - stock.other / stock.queue
  fill:
    to: other
    sensor:
      manual: true
  leak:
    from: other
    driven-by: +stock.other
    equation: stock.other / 2h
""".replace("2h", "two-hours")
    other = "stocks:\n  other:\n    unit: jobs\n    sensor:\n      manual: true\n"
    text = text.replace("parameters:\n", "parameters:\n  two-hours: 2h\n").replace("stocks:\n", other)
    spec, probs = read(tmp_path, text)
    assert not [p for p in probs if p.level == "error"], [str(p) for p in probs if p.level == "error"]
    got = {(r, m.split(",")[0]) for _, m, r in found(spec, "extreme-conditions")}
    msgs = " ".join(m for _, m, _ in found(spec, "extreme-conditions"))
    assert "divides by 0" in msgs and "negative rate" in msgs, got


@pytest.mark.parametrize("demo", ["the-job", "image-squeeze", "software-factory"])
def test_the_demos_pass_the_extreme_conditions_tests(demo):
    from pathlib import Path
    spec, _ = sp.read(Path(__file__).resolve().parent.parent / "examples" / demo / "ergostat.yaml")
    assert not found(spec, "extreme-conditions")


# ---- loop dominance: which loop drives the behaviour, and when

GROWTH = """\
name: g
parameters:
  r: 2
  k: 1
stocks:
  people:
    unit: people
    sensor:
      manual: true
flows:
  births:
    to: people
    driven-by: +stock.people
    equation: r * stock.people
  deaths:
    from: people
    driven-by: +stock.people
    equation: k * stock.people
"""


def test_the_reinforcing_loop_dominates_growth_by_its_share_of_the_change(tmp_path):
    write(tmp_path, GROWTH)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(61):
        p.measurements.add("sensor/people.main", 10 * math.exp((i - 60) / 60), at=now - 3600 + i * 60)
    data = ob.measured(p, ob.Grid(now - 3600, now, 30))
    run = sim.replay(p.model.spec, data)
    got = dm.dominance(p.model.spec, data, run)
    names = {got["polarity"][k]: k for k in got["relative"]}
    late = [v for v in got["relative"][names["R"]][5:] if v is not None]
    assert late and all(v == pytest.approx(2 / 3, rel=1e-3) for v in late)      # r / (r + k)
    assert all(v == pytest.approx(-1 / 3, rel=1e-3) for v in got["relative"][names["B"]][5:] if v is not None)
    assert got["share"][names["R"]] == 1.0 and not got["not_scored"]


def test_a_loop_through_a_decision_with_several_inputs_is_not_scored_and_says_why(tmp_path):
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
    got = dm.dominance(p.model.spec, data, sim.replay(p.model.spec, data))
    assert any("decision with 2 inputs" in w for w in got["not_scored"].values()), got["not_scored"]


def test_a_replay_that_does_not_move_explains_none_of_the_record_whatever_its_rounding():
    from ergostat.numbers import fit as ft
    flat = [132.0 + (1e-12 if i % 3 else 0.0) for i in range(20)]
    got = ft.stats(flat, [250.0 + 10 * (i % 4) for i in range(20)])
    assert got["r2"] == 0.0 and got["still"] and got["says"] == "does not move, while the record does, and runs low"
