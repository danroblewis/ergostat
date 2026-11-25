"""The relative gain array of a system's loops from approved step tests (control/rga.py; SPEC §12d)."""

from __future__ import annotations

import io
import json
import math
import random
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.control import rga, steptest
from ergostat.spec.architecture import _chains
from ergostat.spec.explain import explain
from ergostat.store import Project

G0 = [[1.0, 0.4], [0.5, 1.0]]            # λ11 = 1 / (1 − 0.2) = 1.25
SENSE = "sensor: {run: echo 0, every: 10s}"


def model(loops=2, extra=""):
    """System plant holds goal g1 (in its subsystem inner) and g2 (directly in plant), g3 too with three loops; each
    goal's level is driven by every loop's setting, which its controller steps."""
    out = ["name: rga", "systems:", "  plant: {description: interacting levels}",
           "  inner: {description: the first loop, within: plant}", "  elsewhere: {description: outside}",
           "parameters:", "  leak-time: {value: 2h}", "stocks:"]
    sys_ = lambda i: "inner" if i == 1 else "plant"        # noqa: E731
    drives = ", ".join(f"+stock.s{j}" for j in range(1, loops + 1))
    for i in range(1, loops + 1):
        out += [f"  s{i}: {{unit: q, system: {sys_(i)}, {SENSE}}}", f"  l{i}: {{unit: m, system: {sys_(i)}, {SENSE}}}"]
    out += ["  other: {unit: m, system: elsewhere, sensor: {manual: true}}", "flows:"]
    for i in range(1, loops + 1):
        out += [f"  steps{i}: {{to: s{i}, two-way: true, system: {sys_(i)}}}",
                f"  turn{i}: {{to: l{i}, two-way: true, driven-by: [{drives}, -stock.l{i}], system: {sys_(i)}}}"]
    out += ["  leak: {from: l2, equation: stock.l2 / leak-time, driven-by: [+stock.l2], system: plant}",
            "  away: {from: other, rate: 1, system: elsewhere}", "goals:"]
    for i in range(1, loops + 1):
        out += [f"  g{i}: {{stock: l{i}, hold: '== 5', tolerance: 0.05, system: {sys_(i)}}}"]
    out += ["blocks:"]
    for i in range(1, loops + 1):
        out += [f"  t{i}: {{type: program, run: 'true', in: goal.g{i}.error, every: 10s, gain: 0.5, out: flow.steps{i}, "
                f"system: {sys_(i)}}}"]
    return "\n".join(out) + "\n" + extra


def load(d, text):
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(text)
    return Project(mdl.load(d))


def stamp(spec, goal):
    return {s: rga.plant_signature(spec, s) for s in _chains(spec)[f"goal.{goal}"]}


def record_tests(p, tests, G=G0, compensate=False, tau=30.0, noise=0.003, gap=200, seed=5, us=None, delay=0,
                 ramp=None):
    """A linear plant y = G u (each y lagging by ``tau``) and its step tests, written as the record: each test is a
    dict (``loop`` index, ``amount``, ``hold``, and optionally ``how``, ``stamp``, ``after`` (the finish's stamp),
    ``spec`` (stamped from), ``no_y``: a loop with no y reading in its after window). With ``compensate``, the other
    loop's u moves so its y stays where it was (its controller acting). With ``ramp`` (per second), the plant is an
    integrator instead: dy/dt = ramp · G (u − 25)."""
    m = len(G)
    us = us or [f"s{i + 1}" for i in range(m)]
    rnd = random.Random(seed)
    spans, k = [], gap
    for t in tests:
        spans.append(k)
        k += 2 * t["hold"] + gap
    t0 = int(time.time()) - k - 30.0                     # (whole seconds: the store keeps a time to the ms)
    u, x, hist = [25.0] * m, None, []
    a, ac = math.exp(-1 / tau), math.exp(-1 / 20.0)
    for s in range(k):
        T = t0 + s
        want = [25.0] * m
        for n, (t, s0) in enumerate(zip(tests, spans, strict=True)):
            i, g = t["loop"], f"g{t['loop'] + 1}"
            spec = t.get("spec") or p.model.spec
            if s == s0:
                p.events.add("steptest.started", item=g, source="ergostat", at=T - 1, data={
                    "test": f"x{n}", "amount": t["amount"], "hold": t["hold"], "plant": t.get("stamp", stamp(spec, g))})
                p.events.add("steptest.stepped", item=g, source="ergostat", at=T, data={"test": f"x{n}", "phase": "up"})
            if s == s0 + t["hold"] and not t.get("no_back"):
                p.events.add("steptest.stepped", item=g, source="ergostat", at=T, data={"test": f"x{n}", "phase": "back"})
            if s == s0 + 2 * t["hold"]:
                p.events.add("steptest.finished", item=g, source="ergostat", at=T, data={
                    "test": f"x{n}", "how": t.get("how", "done"), "plant": t.get("after", t.get("stamp", stamp(spec, g)))})
            if s0 <= s < s0 + t["hold"]:
                want[i] += t["amount"]
                if compensate:
                    j = 1 - i
                    want[j] -= G[j][i] / G[j][j] * t["amount"]
        own = next((t["loop"] for t, s0 in zip(tests, spans, strict=True) if s0 <= s < s0 + 2 * t["hold"]), None)
        for i in range(m):              # the stepped u moves at once; the others, acting, follow their controllers
            u[i] = ac * u[i] + (1 - ac) * want[i] if compensate and i != own else want[i]
        hist.append(u[:])
        ud = hist[max(0, s - delay)]
        target = [sum(G[i][j] * ud[j] for j in range(m)) for i in range(m)]
        if ramp is not None:
            x = x or [5.0] * m
            x = [x[i] + ramp * (target[i] - sum(G[i]) * 25.0) for i in range(m)]
        else:
            x = target[:] if x is None else [a * x[i] + (1 - a) * target[i] for i in range(m)]
        if s % 10 == 0:
            for i in range(m):
                p.measurements.add(f"sensor/{us[i]}.main", u[i], T)
                skip = any(t.get("no_y") == i and s0 + t["hold"] * 3 / 4 <= s < s0 + t["hold"]
                           for t, s0 in zip(tests, spans, strict=True))
                if not skip:
                    p.measurements.add(f"sensor/l{i + 1}.main", x[i] + rnd.gauss(0, noise), T + 0.5)
    return p


def two_each(**kw):
    return [{"loop": 0, "amount": 2.0, "hold": 400, **kw}, {"loop": 1, "amount": 2.0, "hold": 400, **kw}]


def lam(r, i=0):
    return r["lambda"][i][i]


# ---- the gains and the relative gain array

def test_two_interacting_loops_give_their_relative_gains(tmp_path):
    p = record_tests(load(tmp_path, model()), two_each())
    r = rga.of(p, p.model.spec, "plant")
    assert r["computed"], r
    assert lam(r, 0) == pytest.approx(1.25, abs=0.02) and lam(r, 1) == pytest.approx(1.25, abs=0.02)
    said = [x for x in explain(p.model.spec, "system.plant", p).splitlines() if "Relative gain" in x]
    assert said == ["  Relative gain array: λ g1 1.25, g2 1.25 (each loop on its own u, from 2 step tests, the gains as "
                    "held over the last quarter of each hold)."]


def test_the_line_is_said_through_the_mcp_explain_tool_and_not_without_a_project(tmp_path):
    from ergostat.mcp import serve
    p = record_tests(load(tmp_path, model()), two_each())
    out = io.StringIO()
    serve(tmp_path, io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "explain", "arguments": {"part": "system.plant"}}}) + "\n"), out)
    text = json.loads(out.getvalue().splitlines()[0])["result"]["content"][0]["text"]
    assert "Relative gain array: λ g1 1.25, g2 1.25" in text
    assert "Relative gain" not in explain(p.model.spec, "system.plant")


def test_the_other_loops_acting_still_give_the_open_loop_gains(tmp_path):
    from ergostat.control import record
    from ergostat.control.loop import tests_in
    p = record_tests(load(tmp_path, model()), two_each(), compensate=True)
    sigs = {g: record.signals(p.model.spec, g) for g in ("g1", "g2")}
    du, dy = rga._moves(p, sigs, tests_in(p, "g1", 0, time.time())[0])
    assert abs(dy[1]) < 0.05 and du[1] == pytest.approx(-1.0, abs=0.05)    # the other loop held its y: Δu2 = −0.5·2
    r = rga.of(p, p.model.spec, "plant")
    assert r["computed"], r
    assert lam(r, 0) == pytest.approx(1.25, abs=0.05) and lam(r, 1) == pytest.approx(1.25, abs=0.05)


# ---- the stamp a step test carries

class FakeEngine:
    def __init__(self, p):
        self.p, self.spec = p, p.model.spec
        self.lock = threading.RLock()
        self.running, self.held, self.testing, self.moved_by = set(), set(), {}, {}
        self.began, self.finished = {}, {}
        self.signals = {"goal.g1.error": 0.0, "stock.s1": 25.0}
        self.stop = threading.Event()

    def run_block(self, b, why):
        cmd = self.testing[b.name]
        was = self.signals["stock.s1"]
        q = cmd["to"] if cmd.get("to") is not None else was + cmd["amount"]
        self.signals["stock.s1"] = q
        self.moved_by[b.name] = {"steps1": q - was}
        return ["steps1"]

    def _read_moved(self, flows, cause, spec=None):
        pass

    def say(self, *_):
        pass


PLAN = {"goal": "g1", "block": "t1", "abort": 1.0, "hold_blocks": ["t1"], "u": "stock.s1", "limits": [5.0, 95.0],
        "resolution": 0.1, "flow": "steps1", "id": "a1", "amount": 3.0, "hold": 0.05}


def test_steptest_run_stamps_every_enclosing_system(tmp_path, monkeypatch):
    p = load(tmp_path, model())
    monkeypatch.setattr(steptest, "POLL", 0.01)
    steptest.run(FakeEngine(p), PLAN)
    spec = p.model.spec
    started = p.events.query(type="steptest.started")[-1]["data"]["plant"]
    assert list(started) == ["inner", "plant"]
    assert started == {"inner": rga.plant_signature(spec, "inner"), "plant": rga.plant_signature(spec, "plant")}
    assert p.events.query(type="steptest.finished")[-1]["data"]["plant"] == started
    from ergostat.control.loop import tests_in
    assert tests_in(p, "g1", 0, time.time())[0]["plant"] == started


def test_steptest_run_writes_no_stamp_when_the_signature_fails(tmp_path, monkeypatch):
    p = load(tmp_path, model())
    monkeypatch.setattr(steptest, "POLL", 0.01)
    monkeypatch.setattr(rga, "plant_signature", lambda *_: 1 / 0)
    steptest.run(FakeEngine(p), PLAN)
    assert p.events.query(type="steptest.started")[-1]["data"]["plant"] is None
    fin = p.events.query(type="steptest.finished")[-1]["data"]
    assert fin["how"] == "done" and fin["plant"] is None


def _changed(tmp_path, old, new, first=0, then=1, us=None):
    """Tests of loop ``first`` stamped from the model ``old``, then two of loop ``then`` from ``new``; the project now
    holds ``new``."""
    was = load(tmp_path / "was", old).model.spec
    p = load(tmp_path / "now", new)
    tests = [{"loop": first, "amount": 2.0, "hold": 400, "spec": was}, {"loop": then, "amount": 2.0, "hold": 400},
             {"loop": then, "amount": -2.0, "hold": 400}]
    return rga.of(record_tests(p, tests, us=us), p.model.spec, "plant")


def test_a_change_elsewhere_in_the_system_leaves_old_tests_out(tmp_path):
    base = model()
    r = _changed(tmp_path, base, base.replace("equation: stock.l2 / leak-time", "equation: stock.l2 / leak-time / 2"))
    assert not r["computed"] and r["why"] == "no usable step test of its own: g1", r
    assert {"goal": "g1", "test": "x0", "why": "system plant has changed since its start"} in r["left"]


def test_a_parameter_change_in_the_system_leaves_old_tests_out(tmp_path):
    base = model()
    r = _changed(tmp_path, base, base.replace("leak-time: {value: 2h}", "leak-time: {value: 3h}"))
    assert not r["computed"] and r["why"] == "no usable step test of its own: g1", r


def test_a_controller_rewired_to_another_actuator_leaves_its_old_tests_out(tmp_path):
    more = model().replace("flows:\n", "flows:\n  steps9: {to: s9, two-way: true, system: plant}\n").replace(
        "stocks:\n", f"stocks:\n  s9: {{unit: q, system: plant, {SENSE}}}\n").replace(
        "driven-by: [+stock.s1, +stock.s2,", "driven-by: [+stock.s1, +stock.s2, +stock.s9,")
    rewired = more.replace("out: flow.steps2,", "out: flow.steps9,")
    r = _changed(tmp_path, more, rewired, first=1, then=0, us=["s1", "s9"])
    assert not r["computed"] and r["why"] == "no usable step test of its own: g2", r


def test_a_change_outside_the_system_keeps_its_tests(tmp_path):
    base = model()
    r = _changed(tmp_path, base, base.replace("away: {from: other, rate: 1,", "away: {from: other, rate: 2,"))
    assert r["computed"] and lam(r) == pytest.approx(1.25, abs=0.02), r


def test_a_change_to_a_controller_gain_keeps_the_tests(tmp_path):
    base = model()
    r = _changed(tmp_path, base, base.replace("every: 10s, gain: 0.5, out: flow.steps1", "every: 10s, gain: 0.8, out: flow.steps1"))
    assert r["computed"] and lam(r) == pytest.approx(1.25, abs=0.02), r


@pytest.mark.parametrize("bad", [None, {}, {"inner": "x"}, {"plant": None}])
def test_a_test_with_no_stamp_is_left_out(tmp_path, bad):
    p = record_tests(load(tmp_path, model()), [{"loop": 0, "amount": 2.0, "hold": 400, "stamp": bad}, *two_each()])
    r = rga.of(p, p.model.spec, "plant")
    assert r["computed"] and r["tests"] == 2
    assert r["left"] == [{"goal": "g1", "test": "x0", "why": "it carries no stamp of system plant at its start"}]


def test_a_change_during_the_test_leaves_it_out(tmp_path):
    p = load(tmp_path, model())
    p = record_tests(p, [{"loop": 0, "amount": 2.0, "hold": 400, "after": {"plant": "other"}}, *two_each()])
    r = rga.of(p, p.model.spec, "plant")
    assert r["left"] == [{"goal": "g1", "test": "x0", "why": "system plant has changed since its finish"}]


def test_none_never_matches_none(tmp_path, monkeypatch):
    p = record_tests(load(tmp_path, model()), two_each(stamp={"plant": None}))
    monkeypatch.setattr(rga, "plant_signature", lambda *_: None)
    assert rga.of(p, p.model.spec, "plant") == {"computed": False, "why": "the system's signature could not be worked out"}
    # the signature now a real string, the stamp None: left out, never matched
    monkeypatch.undo()
    r = rga.of(p, p.model.spec, "plant")
    assert r["why"] == "0 usable step tests, fewer than its 2 loops"
    assert [x["why"] for x in r["left"]] == ["it carries no stamp of system plant at its start"] * 2


def test_an_unworkable_signature_now_is_not_computed(tmp_path, monkeypatch):
    p = record_tests(load(tmp_path, model()), two_each())
    monkeypatch.setattr(rga, "plant_signature", lambda *_: 1 / 0)
    r = rga.of(p, p.model.spec, "plant")
    assert r == {"computed": False, "why": "the system's signature could not be worked out"}
    assert rga.line(r) == "Relative gain array: not computed: the system's signature could not be worked out."


def test_a_test_stopped_early_is_left_out(tmp_path):
    early = {"loop": 0, "amount": 2.0, "hold": 400, "how": "stopped early: the error reached 2"}
    p = record_tests(load(tmp_path, model()), [early, *two_each()])
    r = rga.of(p, p.model.spec, "plant")
    assert r["computed"] and r["tests"] == 2
    assert r["left"] == [{"goal": "g1", "test": "x0", "why": "it did not finish done (stopped early: the error reached 2)"}]


def test_a_test_with_no_step_back_recorded_is_left_out(tmp_path):
    p = record_tests(load(tmp_path, model()), [{"loop": 0, "amount": 2.0, "hold": 400, "no_back": True}, *two_each()])
    r = rga.of(p, p.model.spec, "plant")
    assert r["computed"] and r["tests"] == 2
    assert r["left"] == [{"goal": "g1", "test": "x0", "why": "it has no step up, step back or finish recorded"}]


def test_a_step_not_settled_by_the_end_of_its_hold_is_left_out(tmp_path):
    """A dead time of 320 s in a hold of 400: y is still rising through the last quarter."""
    p = record_tests(load(tmp_path, model()), two_each(), delay=320)
    r = rga.of(p, p.model.spec, "plant")
    assert not r["computed"] and r["why"] == "0 usable step tests, fewer than its 2 loops"
    assert r["left"][0]["why"] == "not settled: stock.l1 still moving at the end of its hold", r


@pytest.mark.parametrize("plant", [{"ramp": 0.005}, {"tau": 200.0}], ids=["undeclared-integrator", "lag-of-half-hold"])
def test_a_ramp_or_a_lag_far_from_settled_is_left_out(tmp_path, plant):
    """An integrator nobody declared (no ``process:``, no ``known``): its y ramps, so the after window's halves differ by
    a seventh of Δ whatever the slope. A lag of half the hold differs by about 0.053 of Δ. Both pass SETTLE = 0.25;
    neither may count as a gain."""
    p = record_tests(load(tmp_path, model()), two_each(), **plant)
    from ergostat.control import record
    assert all(record.signals(p.model.spec, g).known is None and p.model.spec.goals[g].process is None
               for g in ("g1", "g2"))
    r = rga.of(p, p.model.spec, "plant")
    assert not r["computed"] and r["why"] == "0 usable step tests, fewer than its 2 loops", r
    assert [x["test"] for x in r["left"]] == ["x0", "x1"], r
    assert all(x["why"] in ("not settled: stock.l1 still moving at the end of its hold",
                            "not settled: stock.l2 still moving at the end of its hold") for x in r["left"]), r


def test_a_lag_of_a_quarter_of_the_hold_still_counts(tmp_path):
    """SETTLE is not so tight that a lag mostly settled (τ = hold/4: 97% of its gain held) is refused."""
    p = record_tests(load(tmp_path, model()), two_each(), tau=100.0)
    r = rga.of(p, p.model.spec, "plant")
    assert r["computed"] and r["tests"] == 2, r
    assert lam(r, 0) == pytest.approx(1.25, abs=0.05)


def test_a_missing_reading_leaves_the_test_out(tmp_path):
    p = record_tests(load(tmp_path, model()), [{"loop": 0, "amount": 2.0, "hold": 400, "no_y": 1},
                                               {"loop": 1, "amount": 2.0, "hold": 400}])
    r = rga.of(p, p.model.spec, "plant")
    assert not r["computed"] and r["why"] == "1 usable step tests, fewer than its 2 loops"
    assert r["left"] == [{"goal": "g1", "test": "x0", "why": "no reading of stock.l2"}]


# ---- the guards on the mathematics

def test_collinear_moves_are_not_computed():
    r = rga.solve([[1.0, 2.0], [2.0, 4.0]], [[1.0, 1.0], [2.0, 2.0]], ["a", "b"])
    assert r == {"computed": False, "why": "the moves were collinear"}


def test_nearly_collinear_moves_past_cond_are_not_computed():
    r = rga.solve([[1.0, 1.0], [1.0, 1.01]], [[1.0, 1.0], [1.0, 1.01]], ["a", "b"])
    assert not r["computed"] and r["why"].startswith("the moves were nearly collinear (condition number about 4")
    assert "past 100" in r["why"]


def test_singular_gains_are_not_computed():
    r = rga.solve([[1.0, 0.0], [0.0, 1.0]], [[1.0, 2.0], [2.0, 4.0]], ["a", "b"])
    assert r == {"computed": False, "why": "the gains found are singular"}


def test_an_integrating_loop_is_not_computed_and_says_why(tmp_path):
    text = model().replace("g2: {stock: l2, hold: '== 5', tolerance: 0.05,",
                           "g2: {stock: l2, hold: '== 5', tolerance: 0.05, process: {gain: 1, integrating: true},")
    p = record_tests(load(tmp_path, text), two_each())
    assert rga.of(p, p.model.spec, "plant") == {
        "computed": False, "why": "g2 is an integrator, and an integrator has no steady-state gain"}


def test_a_loop_the_model_knows_is_an_integrator_is_not_computed(tmp_path):
    text = model().replace("  away:", "  fill: {to: l2, system: plant}\n  away:").replace(
        "out: flow.steps2,", "out: flow.fill,")
    p = load(tmp_path, text)
    from ergostat.control import record
    assert "integrator" in record.signals(p.model.spec, "g2").known
    assert rga.of(p, p.model.spec, "plant") == {
        "computed": False, "why": "g2 is an integrator, and an integrator has no steady-state gain"}


def test_fewer_usable_tests_than_loops_is_not_computed(tmp_path):
    p = record_tests(load(tmp_path, model()), two_each()[:1])
    r = rga.of(p, p.model.spec, "plant")
    assert r == {"computed": False, "why": "1 usable step tests, fewer than its 2 loops", "left": []}


def test_a_loop_with_no_usable_test_is_named(tmp_path):
    G3 = [[1.0, 0.4, 0.1], [0.5, 1.0, 0.2], [0.1, 0.2, 1.0]]
    tests = [{"loop": 0, "amount": 2.0, "hold": 400}, {"loop": 0, "amount": -2.0, "hold": 400},
             {"loop": 1, "amount": 2.0, "hold": 400}]
    p = record_tests(load(tmp_path, model(3)), tests, G=G3)
    assert rga.of(p, p.model.spec, "plant") == {"computed": False, "why": "no usable step test of its own: g3", "left": []}


def test_more_than_most_loops_is_not_computed(tmp_path, monkeypatch):
    p = load(tmp_path, model(3))
    monkeypatch.setattr(rga, "MOST_LOOPS", 2)
    assert rga.of(p, p.model.spec, "plant") == {"computed": False, "why": "3 loops, more than the 2 it is worked out for"}


def test_a_system_with_fewer_than_two_loops_has_no_line(tmp_path):
    p = record_tests(load(tmp_path, model()), two_each())
    assert rga.of(p, p.model.spec, "inner") is None and rga.line(None) is None
    assert "Relative gain" not in explain(p.model.spec, "system.inner", p)


def test_a_large_relative_gain_says_the_loops_fight():
    """Open-loop steps (the other u held), so ΔU is the identity and COND cannot fire first."""
    g = [[1.0, 0.95], [0.96, 1.0]]                     # λ11 = 1 / (1 − 0.912) ≈ 11.4
    r = rga.solve([[1.0, 0.0], [0.0, 1.0]], [[g[0][0], g[1][0]], [g[0][1], g[1][1]]], ["a", "b"])
    assert r["computed"] and lam(r) == pytest.approx(1 / (1 - 0.912))
    assert r["notes"] == ["the loops fight: a", "the loops fight: b"]


def test_a_negative_relative_gain_says_never_pair_on_it():
    g = [[1.0, 2.0], [1.0, 1.0]]                       # λ11 = 1 / (1 − 2) = −1, λ12 = 2
    r = rga.solve([[1.0, 0.0], [0.0, 1.0]], [[1.0, 1.0], [2.0, 1.0]], ["a", "b"])
    assert [x for row in r["G"] for x in row] == pytest.approx([x for row in g for x in row])
    assert lam(r) == pytest.approx(-1.0) and r["lambda"][0][1] == pytest.approx(2.0)
    assert r["notes"][:2] == ["never pair on a negative relative gain: a", "never pair on a negative relative gain: b"]


def test_a_better_pairing_swapped_is_said():
    # G = [[0.3, 1], [1, 0.3]] (symmetric, so ΔY under unit steps is G itself): λ11 = 0.09 / (0.09 − 1) ≈ −0.099
    r = rga.solve([[1.0, 0.0], [0.0, 1.0]], [[0.3, 1.0], [1.0, 0.3]], ["a", "b"])
    assert lam(r) == pytest.approx(0.09 / (0.09 - 1))
    assert r["notes"][-1] == "swapped, λ 1.10: pair a with b's u instead"
    assert not [x for x in rga.solve([[1.0, 0.0], [0.0, 1.0]], [[1.0, 0.5], [0.4, 1.0]], ["a", "b"])["notes"]]


def test_only_the_latest_tests_are_used(tmp_path, monkeypatch):
    """The oldest two step g1 alone (proportional rows: collinear if used); with the cap at 2 they are not read."""
    tests = [{"loop": 0, "amount": 2.0, "hold": 400}, {"loop": 0, "amount": 1.0, "hold": 400}, *two_each()]
    p = record_tests(load(tmp_path, model()), tests)
    monkeypatch.setattr(rga, "MOST_TESTS", 2)
    read, moves = [], rga._moves
    monkeypatch.setattr(rga, "_moves", lambda p, s, t: read.append(t["id"]) or moves(p, s, t))
    r = rga.of(p, p.model.spec, "plant")
    assert read == ["x2", "x3"] and r["computed"] and lam(r) == pytest.approx(1.25, abs=0.02)
    monkeypatch.setattr(rga, "MOST_TESTS", 12)
    assert rga.MOST_TESTS == 12 and rga.MOST_LOOPS == 8


def test_the_cap_is_for_the_whole_system_and_can_leave_a_loop_s_only_test_out(tmp_path, monkeypatch):
    tests = [{"loop": 1, "amount": 2.0, "hold": 400}, {"loop": 0, "amount": 2.0, "hold": 400},
             {"loop": 0, "amount": -2.0, "hold": 400}]
    p = record_tests(load(tmp_path, model()), tests)
    monkeypatch.setattr(rga, "MOST_TESTS", 2)
    assert rga.of(p, p.model.spec, "plant")["why"] == "no usable step test of its own: g2"
