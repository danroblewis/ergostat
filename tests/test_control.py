"""Control engineering on a loop (SPEC §12c): the process identified from the record, the controller's
law and what the two make (margins, step responses, Bode), performance monitoring, SIMC tuning, and
the proposals the owner accepts: the process written into the goal, a gain, a step test run only once
approved."""

from __future__ import annotations

import math
import random
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.control import ident, lti, monitor, record, steptest, tuning
from ergostat.control import loop as lp
from ergostat.control import proposals as cp
from ergostat.store import Project

TUNE = """\
name: tune
stocks:
  setting:
    unit: q
    sensor:
      run: echo 0
      every: 10s
  level:
    unit: m
    sensor:
      run: echo 0
      every: 10s
flows:
  steps:
    to: setting
    two-way: true
  turnover:
    to: level
    two-way: true
    driven-by: [+stock.setting, -stock.level]
goals:
  level-held:
    stock: level
    hold: "== 5"
    tolerance: 0.05
    description: the level held
blocks:
  tuner:
    type: program
    run: "true"
    in: goal.level-held.error
    every: 10s
    gain: 0.5                 # q a step per unit of error
    out: flow.steps
"""

K, TAU, THETA, H = 0.2, 60.0, 20.0, 10.0


def fopdt_record(n=720, seed=3, noise=0.004, step_every=24):
    rnd = random.Random(seed)
    u, v = [], 25.0
    for k in range(n):
        if k % step_every == 0:
            v = 25.0 + rnd.choice([-6, -3, 3, 6])
        u.append(v)
    x = ident.filtered(u, H, TAU, THETA)
    y = [K * a + rnd.gauss(0, noise) for a in x]
    return u, y


def tune_project(tmp_path, **kw):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    u, y = fopdt_record(**kw)
    t0 = time.time() - len(u) * H
    for k, (a, b) in enumerate(zip(u, y, strict=True)):
        p.measurements.add("sensor/setting.main", a, t0 + k * H)
        p.measurements.add("sensor/level.main", b, t0 + k * H + 0.5)
    return p


# ---- the mathematics, against the textbooks

def test_simc_pi_on_a_first_order_process_with_dead_time_has_skogestads_margins():
    p = {"form": "fopdt", "K": 1.0, "tau": 10.0, "theta": 2.0}
    c = tuning.simc(p, "PI")
    assert c["Kc"] == pytest.approx(2.5) and c["Ti"] == pytest.approx(10.0)
    m = lti.margins(p, c)
    assert m["gain_margin"] == pytest.approx(3.14, abs=0.02)          # Skogestad (2003), τc = θ: GM 3.14, PM 61.4°
    assert m["phase_margin"] == pytest.approx(61.4, abs=0.5)
    assert m["ms"] == pytest.approx(1.59, abs=0.02) and m["stable"]


def test_a_gain_past_the_margin_does_not_settle():
    p = {"form": "fopdt", "K": 1.0, "tau": 10.0, "theta": 2.0}
    assert not lti.closed_stable(p, {"form": "PI", "Kc": 2.5 * 3.4, "Ti": 10.0, "T": None})
    assert lti.closed_stable(p, {"form": "PI", "Kc": 2.5 * 2.8, "Ti": 10.0, "T": None})


def test_the_step_responses_say_overshoot_and_settling():
    st = lti.process_step({"form": "fopdt", "K": 2.0, "tau": 10.0, "theta": 3.0})
    assert st["y"][0] == 0 and st["y"][-1] == pytest.approx(2.0, rel=0.01)
    cl = lti.closed_step({"form": "fopdt", "K": 1.0, "tau": 10.0, "theta": 2.0}, {"form": "PI", "Kc": 2.5, "Ti": 10.0, "T": None})
    assert 0 < cl["overshoot"] < 0.15 and cl["settling"] < 30 and cl["y"][-1] == pytest.approx(1.0, abs=0.02)


def test_a_sampled_integral_controller_tuned_by_simc_settles_with_margin():
    p = {"form": "fopdt", "K": K, "tau": TAU, "theta": THETA}
    s = tuning.simc(p, "I", T=H)
    assert s["g"] == pytest.approx(H / (K * 2 * (THETA + H / 2 + TAU)))
    m = lti.margins(p, s)
    assert m["stable"] and m["gain_margin"] > 2.5 and 45 < m["phase_margin"] < 80


def test_the_bode_plot_of_a_delay_falls_in_phase_without_end():
    b = lti.bode({"form": "fopdt", "K": 1.0, "tau": 1.0, "theta": 5.0})
    assert b["process"]["mag"][0] == pytest.approx(1.0, abs=0.01)
    assert b["process"]["phase"][-1] < -360                             # unwrapped, never folded back


# ---- identification

def test_a_first_order_process_with_dead_time_is_identified_and_validated():
    u, y = fopdt_record()
    t = [k * H for k in range(len(u))]
    r = ident.identify(H, t, u, y)
    assert r["form"] == "fopdt" and r["proposable"], r["why"]
    assert r["K"] == pytest.approx(K, rel=0.05) and r["tau"] == pytest.approx(TAU, rel=0.15)
    assert r["theta"] == pytest.approx(THETA, abs=H)
    assert r["fit_val"] > 90 and r["se"]["K"] < 0.05 * K
    assert r["whiteness"]["white"] and r["independence"]["ok"]           # white noise left: both tests pass


def test_a_measured_disturbance_is_fitted_beside_u_not_blamed_on_it():
    u, y = fopdt_record()
    d = [0.5 + 0.4 * math.sin(k / 15) for k in range(len(u))]
    dx = ident.filtered(d, H, TAU, THETA)
    y2 = [a - 0.3 * b for a, b in zip(y, dx, strict=True)]
    t = [k * H for k in range(len(u))]
    alone = ident.identify(H, t, u, y2)
    both = ident.identify(H, t, u, y2, {"auxiliary.mix": d})
    assert both["K"] == pytest.approx(K, rel=0.05) and both["gains"]["auxiliary.mix"] == pytest.approx(-0.3, rel=0.1)
    assert both["fit_val"] > alone["fit_val"]


def test_a_setting_that_never_moved_identifies_nothing_and_says_so():
    t = [k * H for k in range(200)]
    r = ident.identify(H, t, [10.0] * 200, [1.0 + 0.01 * math.sin(k) for k in range(200)])
    assert not r["found"] and "did not move" in r["why"][0]


def test_a_record_too_short_or_too_noisy_is_not_proposed_and_says_why():
    u, y = fopdt_record(n=60, noise=0.2)
    r = ident.identify(H, [k * H for k in range(60)], u, y)
    assert not r["proposable"] and r["why"]


def test_a_lag_longer_than_the_record_is_an_integrator():
    n = 400
    u = [1.0 if (k // 40) % 2 else -1.0 for k in range(n)]
    x = ident.filtered(u, H, None, 30.0)
    y = [0.01 * a + random.Random(k).gauss(0, 0.01) for k, a in enumerate(x)]
    r = ident.identify(H, [k * H for k in range(n)], u, y)
    assert r["form"] == "integrating" and r["K"] == pytest.approx(0.01, rel=0.1) and r["theta"] == pytest.approx(30, abs=H)


# ---- performance monitoring

def test_the_harris_index_of_an_autoregressive_error_is_its_minimum_variance_share():
    rnd = random.Random(1)
    e, x = [], 0.0
    for _ in range(4000):
        x = 0.9 * x + rnd.gauss(0, 1)
        e.append(x)
    one = monitor.harris(e, 1)
    assert one["index"] == pytest.approx(1 - 0.81, abs=0.03)              # σ²_w / (σ²_w / (1 − φ²))
    assert monitor.harris(e, 6)["index"] > 0.6                            # a long dead time: little any controller could remove


def test_a_regular_oscillation_is_found_with_its_period_and_noise_is_not():
    t = [k * 5.0 for k in range(400)]
    osc = monitor.oscillation(t, [0.3 * math.sin(2 * math.pi * x / 120) for x in t], 0.05)
    assert osc["oscillating"] and osc["period"] == pytest.approx(120, rel=0.05) and osc["amplitude"] == pytest.approx(0.3, rel=0.1)
    rnd = random.Random(2)
    assert not monitor.oscillation(t, [rnd.gauss(0, 0.3) for _ in t], 0.05)["oscillating"]


def test_settling_and_overshoot_of_each_time_it_went_off_and_came_back():
    t = [float(k) for k in range(300)]
    e = [0.0] * 300
    for k in range(50, 80):
        e[k] = -1.0                       # off by 1 for 30 s
    for k in range(80, 90):
        e[k] = 0.2                        # past the setpoint on the other side, inside the band
    ex = monitor.excursions(t, e, "==", 0.3, hold_for=20)
    assert ex["count"] == 1 and ex["settling"] == pytest.approx(30) and ex["overshoot"] == pytest.approx(0.2)


# ---- the model: a goal's process, a block's law

def test_a_goals_process_and_a_blocks_gain_are_read(tmp_path):
    text = TUNE.replace("    description: the level held\n", "    description: the level held\n    process:\n      gain: 0.2\n"
                        "      time-constant: 1m\n      dead-time: 20s\n      identified: \"2026-11-16\"\n")
    (tmp_path / "ergostat.yaml").write_text(text)
    spec, probs = sp.read(tmp_path / "ergostat.yaml")
    assert not [x for x in probs if x.level == "error"], probs
    pr = spec.goals["level-held"].process
    assert pr["form"] == "fopdt" and pr["gain"] == 0.2 and pr["tau"] == 60 and pr["theta"] == 20 and pr["identified"] == "2026-11-16"
    assert spec.blocks["tuner"].params["gain"] == 0.5


@pytest.mark.parametrize("bad, says", [("      gain: 0.2\n", "time-constant"), ("      time-constant: 1m\n", "gain"),
                                       ("      gain: 1\n      integrating: true\n      time-constant: 1m\n", "integrator"),
                                       ("      gain: 1\n      time-constant: 1m\n      lag: 3s\n", "unknown key")])
def test_a_process_that_does_not_say_enough_is_refused(tmp_path, bad, says):
    (tmp_path / "ergostat.yaml").write_text(TUNE.replace("    description: the level held\n",
                                                         "    description: the level held\n    process:\n" + bad))
    _, probs = sp.read(tmp_path / "ergostat.yaml")
    assert any(says in str(x) for x in probs if x.level == "error"), probs


def test_a_machine_block_is_given_its_law_in_its_input(tmp_path):
    from ergostat.spec.engine import Engine
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    eng = Engine(Project(mdl.load(tmp_path)), say=lambda *_: None)
    assert eng.context(eng.spec.blocks["tuner"], "schedule")["params"] == {"gain": 0.5}


def test_the_diagram_draws_the_process_the_model_declares(tmp_path):
    from ergostat.blockdiagram import diagram
    text = TUNE.replace("    description: the level held\n", "    description: the level held\n    process:\n      gain: 0.2\n"
                        "      time-constant: 1m\n      dead-time: 20s\n")
    (tmp_path / "ergostat.yaml").write_text(text)
    g = diagram(mdl.load(tmp_path))
    n = next(x for x in g["nodes"] if x.get("y_of") == ["level-held"])
    assert n["fn"]["frac"] == ["0.2 e^(−20s)", "60s + 1"] and "declared" in n["says"]
    tuner = next(x for x in g["nodes"] if x["id"] == "blk:tuner")
    assert tuner["fn"]["expr"] == "0.5/(z − 1)"


# ---- the loop, end to end: identified, proposed, accepted, tuned

def test_a_loop_is_identified_and_its_process_accepted_into_the_goal(tmp_path):
    p = tune_project(tmp_path)
    sig = record.signals(p.model.spec, "level-held")
    assert (sig.u, sig.how, sig.blocks, sig.period) == ("stock.setting", "setting", ["tuner"], 10.0)
    a = lp.analyse(p, "level-held")
    r = a["identified"]
    assert r["proposable"], r["why"]
    assert r["K"] == pytest.approx(K, rel=0.1) and r["theta"] == pytest.approx(THETA, abs=H)
    assert a["controller"]["law"] == {"form": "I", "g": 0.5, "T": 10.0}
    assert a["margins"]["gain_margin"] > 1 and a["closed_step"]["t"]
    assert a["tuning"]["why"].startswith("the process it is tuned for is not in the model")
    offered = cp.offered(p, a)
    kinds = [x["kind"] for x in offered]
    assert kinds == ["process"], kinds                                       # nothing else until the process is in the model
    x = offered[0]
    assert "closed loop" in x["reason"] and "+     process:" in x["edit"]["diff"]
    before = (tmp_path / "ergostat.yaml").read_text()
    cp.accept(p, x["id"])
    after = (tmp_path / "ergostat.yaml").read_text()
    assert after.startswith(before.split("blocks:")[0].split("    description: the level held\n")[0])
    assert "# q a step per unit of error" in after                       # the rest of the file as it was
    pr = p.model.spec.goals["level-held"].process
    assert pr["gain"] == pytest.approx(K, rel=0.1) and pr["identified"]
    assert p.events.query(type="model.accepted")[-1]["data"]["kind"] == "process"
    with pytest.raises(cp.ProposalError):
        cp.accept(p, x["id"])                                               # once only

    a2 = lp.analyse(p, "level-held")
    assert a2["process_from"] == "model" and a2["declared"]["identified"]
    tun = [y for y in cp.offered(p, a2) if y["kind"] == "tuning"]
    assert len(tun) == 1 and "SIMC" in tun[0]["title"], a2["tuning"]
    g_new = tun[0]["values"]["g"]
    cp.accept(p, tun[0]["id"])
    assert p.model.spec.blocks["tuner"].params["gain"] == pytest.approx(g_new, rel=1e-3)
    assert "# q a step per unit of error" in (tmp_path / "ergostat.yaml").read_text()


def test_a_dismissed_proposal_is_not_offered_again_until_the_loop_changes(tmp_path):
    p = tune_project(tmp_path)
    a = lp.analyse(p, "level-held")
    x = cp.offered(p, a)[0]
    cp.dismiss(p, x["id"])
    assert not [y for y in cp.offered(p, lp.analyse(p, "level-held")) if y["kind"] == "process"]


def test_a_loop_the_record_cannot_identify_is_offered_a_step_test_only_approved_while_running(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    t0 = time.time() - 600
    for k in range(60):                                                      # the setting never moved
        p.measurements.add("sensor/setting.main", 25.0, t0 + k * 10)
        p.measurements.add("sensor/level.main", 5.0 + 0.01 * math.sin(k), t0 + k * 10)
    a = lp.analyse(p, "level-held")
    tests = [x for x in cp.offered(p, a) if x["kind"] == "step-test"]
    assert len(tests) == 1
    pl = tests[0]["plan"]
    assert pl["block"] == "tuner" and pl["hold_blocks"] == ["tuner"] and pl["hold"] >= 120 and pl["amount"]
    with pytest.raises(cp.ProposalError, match="not running"):
        cp.accept(p, tests[0]["id"])
    assert not p.events.query(type="steptest.approved")


class FakeEngine:
    """What steptest.run uses of an engine: a block run records its command; the goal's error is set."""

    def __init__(self, p, error=0.0):
        self.p, self.spec = p, p.model.spec
        self.lock = threading.RLock()
        self.running, self.held, self.testing = set(), set(), {}
        self.began, self.finished, self.signals = {}, {}, {"goal.level-held.error": error}
        self.stop = threading.Event()
        self.moves: list[float] = []

    def run_block(self, b, why):
        assert why == "step-test" and b.name in self.held
        self.moves.append(self.testing[b.name]["amount"])
        return []

    def after_acting(self, flows):
        return []

    def say(self, *_):
        pass


def test_an_approved_step_test_holds_the_controller_steps_and_steps_back(tmp_path, monkeypatch):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    monkeypatch.setattr(steptest, "POLL", 0.01)
    eng = FakeEngine(p)
    plan = {"id": "t1", "goal": "level-held", "block": "tuner", "amount": 3.0, "hold": 0.05, "abort": 1.0, "hold_blocks": ["tuner"]}
    steptest.run(eng, plan)
    assert eng.moves == [3.0, -3.0] and not eng.held
    types = [e["type"] for e in p.events.query(type="steptest.*")]
    assert types == ["steptest.started", "steptest.stepped", "steptest.stepped", "steptest.finished"]
    assert p.events.query(type="steptest.finished")[-1]["data"]["how"] == "done"


def test_a_step_test_steps_back_at_once_when_the_error_passes_its_bound(tmp_path, monkeypatch):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    monkeypatch.setattr(steptest, "POLL", 0.01)
    eng = FakeEngine(p, error=2.0)
    steptest.run(eng, {"id": "t2", "goal": "level-held", "block": "tuner", "amount": 3.0, "hold": 30, "abort": 1.0})
    assert eng.moves == [3.0, -3.0]
    assert p.events.query(type="steptest.finished")[-1]["data"]["how"].startswith("stopped early: the error reached 2")


def test_a_held_block_is_not_started_by_its_schedule(tmp_path):
    from ergostat.spec.engine import Engine
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    eng = Engine(Project(mdl.load(tmp_path)), say=lambda *_: None)
    eng.held.add("tuner")
    eng.start(eng.spec.blocks["tuner"], "schedule")
    assert "tuner" not in eng.running


def test_an_approval_from_before_ergostat_started_is_not_run(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    p = Project(mdl.load(tmp_path))
    p.events.add("steptest.approved", item="level-held", source="owner", at=time.time() - 3600,
                 data={"id": "old", "goal": "level-held", "block": "tuner", "amount": 1.0, "hold": 1})
    eng = FakeEngine(p)
    steptest.resume(eng)
    assert eng.moves == [] and "not run" in p.events.query(type="steptest.finished")[-1]["data"]["how"]


def test_the_page_api_answers_and_writes_only_through_the_owners_answer(tmp_path):
    from ergostat.web import control_api
    from ergostat.web.server import Live, api
    p = tune_project(tmp_path)
    live = Live(p)
    d = api(live, "loop-control", {"goal": ["level-held"]})
    assert d["identified"]["proposable"] and d["bode"]["w"] and d["performance"]["harris"]
    pid = d["proposals"][0]["id"]
    code, got = control_api.post(live, f"control/{pid}/accept")
    assert code == 200 and got["status"] == "accepted"
    assert control_api.post(live, f"control/{pid}/accept")[0] == 409
    assert control_api.post(live, "control/x/explode")[0] == 404


def test_the_process_edit_keeps_the_files_comments_and_replaces_an_old_process(tmp_path):
    text = TUNE.replace("    description: the level held\n", "    description: the level held\n    process:     # old\n"
                        "      gain: 9\n      time-constant: 1h\n    critical: false\n")
    (tmp_path / "ergostat.yaml").write_text(text)
    spec, _ = sp.read(tmp_path / "ergostat.yaml")
    e = cp.process_edit(spec, "level-held", ["gain: 0.2", "time-constant: 60s", "dead-time: 20s"])
    from ergostat.numbers import yamledit as ye
    new = ye.apply(e)
    assert "gain: 9" not in new and "      gain: 0.2" in new and "    critical: false" in new and "# q a step" in new
    (tmp_path / "ergostat.yaml").write_text(new)
    spec2, probs = sp.read(tmp_path / "ergostat.yaml")
    assert spec2.goals["level-held"].process["tau"] == 60 and not [x for x in probs if x.level == "error"]
