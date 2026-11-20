"""The model's numbers (SPEC §7b, §12b): equations and parameters, their checks, the replay and the
projection, the fit (R², MAPE, Theil's U_M, U_S, U_C), estimates, and proposals accepted as the
smallest edit to the YAML."""

from __future__ import annotations

import json
import math
import re
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.numbers import estimate as es
from ergostat.numbers import fit as ft
from ergostat.numbers import proposals as pr
from ergostat.numbers import simulate as sim
from ergostat.numbers import version as ver
from ergostat.numbers import yamledit as ye
from ergostat.spec import equation as eq
from ergostat.store import Project

QUEUE = """\
name: q
# the queue drains at k an hour of what is in it
parameters:
  k:
    value: 2          # what we believe
    unit: 1/h
    estimate: true
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals:
    to: queue
    sensor:
      manual: true
  served:
    from: queue
    driven-by: +stock.queue
    equation: k * stock.queue
"""


def write(tmp_path, text: str):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return tmp_path / "ergostat.yaml"


def problems(tmp_path, text: str):
    spec, probs = sp.read(write(tmp_path, text))
    return spec, probs


def errors(probs):
    return [p for p in probs if p.level == "error"]


def codes(probs):
    return {p.code for p in probs}


def queue_project(tmp_path, k_true: float = 3.0, text: str = QUEUE, minutes: int = 120):
    """The queue model, and a record of it as the world ran it with k_true: a reading every 30 s."""
    write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    q = 0.0
    for i in range(minutes * 2 + 1):
        t = now - minutes * 60 + i * 30
        a = 10 + 5 * ((i // 20) % 2)
        p.measurements.add("sensor/queue.main", q, at=t)
        p.measurements.add("sensor/arrivals.main", a, at=t)
        for _ in range(30):
            q += (a - k_true * q) / 3600
    return p, {"at": now, "window": minutes * 60.0, "starts": now - minutes * 60}


# ---- equations

def test_an_equation_reads_with_hyphenated_names_precedence_and_functions():
    t = eq.parse("base + k * stock.unreviewed-ramps-live")
    assert t == ("bin", "+", ("par", "base"), ("bin", "*", ("par", "k"), ("ref", "stock", "unreviewed-ramps-live")))
    assert eq.text(eq.parse("(a - b) / c ^ 2")) == "(a - b) / c^2"
    assert eq.text(eq.parse("a - (b - c)")) == "a - (b - c)"
    assert eq.parse("-x ^ 2") == ("neg", ("bin", "^", ("par", "x"), ("num", 2.0)))
    assert eq.refs(eq.parse("MIN(stock.a, flow.b) + DELAY1(flow.c, t)")) == ["stock.a", "flow.b", "flow.c"]
    assert eq.instant_refs(eq.parse("MIN(stock.a, flow.b) + DELAY1(flow.c, t)")) == ["stock.a", "flow.b"]
    with pytest.raises(eq.EquationError, match="not a function"):
        eq.parse("frob(1)")
    with pytest.raises(eq.EquationError, match="takes 2"):
        eq.parse("DELAY1(x)")
    with pytest.raises(eq.EquationError):
        eq.parse("a +")


def run_eq(text, values, params=None, tables=None, steps=0, dt=0.01):
    c = eq.Compiled(eq.parse(text, {n: type("P", (), {"table": t})() for n, t in (tables or {}).items()}), tables)
    S, D = [0.0] * c.slots, [0.0] * c.slots
    out = c.fn(values, params or {}, S, D, True)
    for _ in range(steps):
        for i in range(len(S)):
            S[i] += dt * D[i]
        out = c.fn(values, params or {}, S, D, False)
    return out


def test_delays_start_in_equilibrium_and_follow_their_input_as_system_dynamics_says():
    v = {"flow.x": 1.0}
    assert run_eq("DELAY1(flow.x, 2)", v) == pytest.approx(1.0)
    v0 = {"flow.x": 0.0}
    c = eq.Compiled(eq.parse("DELAY1(flow.x, 2)"))
    S, D = [0.0], [0.0]
    c.fn(v0, {}, S, D, True)                              # in equilibrium at 0, then a step to 1
    for _ in range(200):                                  # 2 h at 0.01 h: one delay time
        out = c.fn(v, {}, S, D, False)
        S[0] += 0.01 * D[0]
    assert out == pytest.approx(1 - math.exp(-1), abs=0.01)
    c3 = eq.Compiled(eq.parse("SMOOTH3(flow.x, 2)"))
    S3, D3 = [0.0] * 3, [0.0] * 3
    c3.fn(v0, {}, S3, D3, True)
    for _ in range(200):
        out3 = c3.fn(v, {}, S3, D3, False)
        for i in range(3):
            S3[i] += 0.01 * D3[i]
    assert 0 < out3 < out                                 # a third-order delay is slower to start
    assert run_eq("effect(stock.q)", {"stock.q": 5}, tables={"effect": [(0.0, 1.0), (10.0, 0.0)]}) == pytest.approx(0.5)
    assert run_eq("effect(stock.q)", {"stock.q": 50}, tables={"effect": [(0.0, 1.0), (10.0, 0.0)]}) == 0.0   # flat past its end
    assert run_eq("1 / stock.q", {"stock.q": 0}) == 0.0   # ZIDZ


def test_units_multiply_divide_and_say_where_they_disagree():
    u = eq.unit
    assert u("alerts/ramp/workday") == {"alert": 1, "ramp": -1, "workday": -1}
    assert u("ramps") == u("ramp") and u("hypotheses") == u("hypothesis") and u("share") == {} and u("1/h") == {"h": -1}
    tree = eq.parse("workdays-per-hour * (base + per-ramp * stock.live)")
    units = {"workdays-per-hour": u("workdays/h"), "base": u("alerts/workday"), "per-ramp": u("alerts/ramp/workday")}
    got, probs = eq.units_of(tree, lambda r: u("ramps"), units.get)
    assert got == u("alerts/h") and not probs
    _, probs = eq.units_of(eq.parse("stock.a + stock.b"), {"stock.a": u("jobs"), "stock.b": u("users")}.get, lambda n: None)
    assert probs and "adds unlike things" in probs[0]
    got, probs = eq.units_of(eq.parse("2 * stock.a + 1"), lambda r: u("jobs"), lambda n: None)
    assert got == u("jobs") and not probs                 # a number takes the unit it needs


# ---- compiling

def test_parameters_compile_short_form_and_durations_in_hours(tmp_path):
    spec, probs = problems(tmp_path, QUEUE.replace("parameters:\n", "parameters:\n  t: 30m\n  w:\n    value: 40s\n"))
    assert not errors(probs)
    assert spec.parameters["t"].value == 0.5 and spec.parameters["w"].value == pytest.approx(40 / 3600)
    assert spec.parameters["w"].unit == "h" and spec.parameters["t"].value_at.line == spec.parameters["t"].defined.line
    assert spec.flows["served"].equation.parameters == ["k"] and spec.flows["served"].equation.refs == ["stock.queue"]
    assert spec.parameters["k"].provenance == "declared"
    assert "parameter-unused" in codes(probs)


@pytest.mark.parametrize("change,message", [
    (("k * stock.queue", "k-j * stock.queue"), "k-j is not a parameter"),
    (("k * stock.queue", "k * stock.nope"), "'nope' is not a stock"),
    (("k * stock.queue", "k * flow.served"), "names itself"),
    (("k * stock.queue", "k * (stock.queue"), "expected ')'"),
    (("    equation: k * stock.queue\n", "    equation: k * stock.queue\n    rate: 3\n"), "written twice"),
])
def test_an_equation_that_is_wrong_is_refused_with_its_line(tmp_path, change, message):
    _, probs = problems(tmp_path, QUEUE.replace(*change))
    errs = errors(probs)
    assert errs and message in errs[0].message and errs[0].where.line == 21, [str(e) for e in errs]


def test_minus_without_spaces_says_how_to_subtract(tmp_path):
    text = QUEUE.replace("parameters:\n", "parameters:\n  j: 1\n").replace("k * stock.queue", "k-j")
    _, probs = problems(tmp_path, text)
    assert "write spaces around the minus: k - j" in errors(probs)[0].message


def test_equations_that_need_each_other_at_once_are_an_algebraic_loop_unless_a_delay_is_between(tmp_path):
    text = QUEUE + "auxiliaries:\n  a:\n    equation: auxiliary.b + 1\n  b:\n    equation: auxiliary.a * 2\n"
    _, probs = problems(tmp_path, text)
    assert any(e.code == "algebraic-loop" for e in errors(probs))
    _, probs = problems(tmp_path, text.replace("auxiliary.a * 2", "SMOOTH(auxiliary.a, 1)"))
    assert not errors(probs)


def test_findings_on_numbers_units_sizes_links_and_parameters(tmp_path):
    text = QUEUE.replace("unit: 1/h\n", "unit: 1/shift\n") + """\
  other:
    to: queue
    driven-by: [+stock.queue]
    equation: lost * 2
auxiliaries:
  load:
    unit: jobs
    equation: stock.queue
"""
    text = text.replace("parameters:\n", "parameters:\n  lost:\n    unit: jobs/h\n")
    _, probs = problems(tmp_path, text)
    assert not errors(probs), [str(e) for e in errors(probs)]
    said = {p.code: p.message for p in probs}
    assert "job/shift" in said["equation-units"]
    assert "size-unknown" in said and "other" in said["size-unknown"]
    assert "equation-not-drawn" in said and "stock.queue" in said["equation-not-drawn"]
    assert "parameter-unknown" in said and "lost" in said["parameter-unknown"]
    assert "auxiliary-without-causes" not in codes(probs)            # its equation is its cause


def test_a_time_in_minutes_days_or_seconds_is_refused_not_read_as_hours(tmp_path):
    """The model's time is hours: 30 with unit min would be read as 30 hours, a sixty-fold error."""
    for unit in ("min", "1/day", "jobs/s", "weeks"):
        _, probs = problems(tmp_path, QUEUE.replace("unit: 1/h\n", f"unit: {unit}\n"))
        [e] = errors(probs)
        assert "the model's time is hours" in e.message and "value: 30m" in e.message, unit
    _, probs = problems(tmp_path, QUEUE.replace("unit: 1/h\n", "unit: ms\n"))        # a latency is a quantity
    assert not errors(probs)


def test_an_equation_whose_effect_has_the_other_sign_from_its_link_is_found(tmp_path):
    """Link polarity is the sign of the partial derivative (Sterman ch. 5.2): checked across a range."""
    wrong = QUEUE.replace("equation: k * stock.queue", "equation: k * (10 - stock.queue)")
    _, probs = problems(tmp_path, wrong)
    said = [p.message for p in probs if p.code == "equation-sign"]
    assert len(said) == 1 and "the other way" in said[0] and "+stock.queue" in said[0]
    turns = QUEUE.replace("equation: k * stock.queue", "equation: k * (stock.queue - 3) ^ 2")
    _, probs = problems(tmp_path, turns)
    assert any(p.code == "equation-sign" and "changes sign" in p.message for p in probs)
    _, probs = problems(tmp_path, QUEUE)
    assert "equation-sign" not in codes(probs)
    smooth = QUEUE.replace("driven-by: +stock.queue\n    equation: k * stock.queue",
                           "driven-by: [+stock.queue]\n    equation: SMOOTH(stock.queue, 2) * k")
    _, probs = problems(tmp_path, smooth)
    assert "equation-sign" not in codes(probs)                     # through a delay, in equilibrium: the same sign


# ---- versions

def test_the_structure_ignores_values_and_the_version_does_not(tmp_path):
    a = sp.load(write(tmp_path, QUEUE))
    b = sp.load(write(tmp_path, QUEUE.replace("value: 2", "value: 3")))
    c = sp.load(write(tmp_path, QUEUE.replace("k * stock.queue", "k * stock.queue * 2")))
    assert ver.structure(a) == ver.structure(b) != ver.structure(c)
    assert ver.version(a) != ver.version(b)


# ---- the replay, the projection and the fit

def test_the_replay_integrates_the_stock_from_its_equation_and_its_measured_inflow(tmp_path):
    p, snap = queue_project(tmp_path, k_true=2.0)                # the model's k is the world's
    data, run, got = ft.compute(p, snap)
    s = got["stocks"]["stock.queue"]
    assert s["r2"] > 0.999 and s["error_share"] < 0.02 and s["mape"] is None, s     # it starts at 0: MAPE says nothing
    assert not s.get("too_little") and s["error_of"] == "mean"
    assert run.how == {"stock.queue": "integrated", "flow.served": "equation"}
    assert not run.notes
    proj = sim.project(p.model.spec, data, run, 3600)
    vals = [v for v in proj.values["stock.queue"] if v is not None]
    q0, a = data.last("stock.queue"), data.last("flow.arrivals")  # the inflow held where it was, k = 2: toward a / 2
    assert vals[-1] == pytest.approx(a / 2 + (q0 - a / 2) * math.exp(-2), rel=0.02)


def test_a_wrong_parameter_shows_as_bias_in_theils_statistics(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)                # the model drains too slowly: it runs high
    _, _, got = ft.compute(p, snap)
    s = got["stocks"]["stock.queue"]
    assert s["um"] > 0.5 and s["mean_replay"] > s["mean_measured"]
    assert s["um"] + s["us"] + s["uc"] == pytest.approx(1.0)
    assert got["total"]["stocks"] == 1


def test_theils_statistics_split_the_error_and_sum_to_one():
    meas = [math.sin(i / 5) for i in range(100)]
    biased = ft.stats([m + 1 for m in meas], meas)
    assert biased["um"] == pytest.approx(1.0) and biased["r2"] == pytest.approx(1.0)
    swung = ft.stats([2 * m for m in meas], meas)
    assert swung["us"] > 0.9
    late = ft.stats([math.sin((i - 8) / 5) for i in range(100)], meas)
    assert late["uc"] > 0.9
    for s in (biased, swung, late):
        assert s["um"] + s["us"] + s["uc"] == pytest.approx(1.0)
    assert ft.stats([1, 2, 3], [1, 2, 3])["exact"] and ft.stats([1, 2], [1, 2]) is None


def test_a_parameter_with_no_value_leaves_its_equation_out_and_its_part_taken_as_measured(tmp_path):
    p, snap = queue_project(tmp_path, text=QUEUE.replace("    value: 2          # what we believe\n", ""))
    _, run, _ = ft.compute(p, snap)
    assert "flow.served" not in run.how and any("k has no value" in n for n in run.notes)


def test_the_fit_is_recorded_per_version_at_most_every_few_minutes(tmp_path):
    p, snap = queue_project(tmp_path)
    _, _, got = ft.compute(p, snap)
    assert ft.record(p, got, 3600) and ft.record(p, got, 3600) is None
    assert ft.record(p, got, 3600, force=True)
    rows = ft.versions(p)
    assert len(rows) == 1 and rows[0]["fits"] == 2 and rows[0]["version"] == ver.version(p.model.spec)


# ---- estimates

def test_an_estimate_recovers_the_parameter_and_is_kept_apart_from_the_yaml(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    got = es.estimate(p, snap)["k"]
    assert got["value"] == pytest.approx(3.0, rel=0.02) and got["after"] < got["before"] / 100
    assert got["n"] > 80 and got["fitted_to"] == ["stock.queue"]                  # the last fifth held out
    assert got["se"] < 0.01 and got["held_after"] < got["held_before"] and not got["at_bound"]
    assert "value: 2" in (tmp_path / "ergostat.yaml").read_text()          # nothing written to the model
    assert es.load(p, p.model.spec)["k"]["value"] == got["value"]
    assert (p.dir / "estimates" / f"{ver.structure(p.model.spec)}.json").exists()


def test_nelder_mead_finds_a_minimum():
    x, f = es.nelder_mead(lambda v: (v[0] - 3) ** 2 + (v[1] + 1) ** 2, [0.0, 0.0], [1.0, 1.0], iterations=300)
    assert x[0] == pytest.approx(3, abs=1e-3) and x[1] == pytest.approx(-1, abs=1e-3) and f < 1e-6


# ---- proposals, and the edit that accepts one

def test_a_proposal_says_why_shows_the_fit_before_and_after_and_its_edit(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    [x] = pr.make(p, snap)
    assert x["kind"] == "parameter" and x["parameters"]["k"] == pytest.approx(3.0, rel=0.01) and x["previous"] == {"k": 2.0}
    assert x["parts"] == ["flow.served"] and "estimated from" in x["reason"]
    assert x["fit_after"]["total"]["nmse"] < x["fit_before"]["total"]["nmse"]
    assert x["objective"]["after"] < x["objective"]["before"] and x["objective"]["held_after"] < x["objective"]["held_before"]
    assert x["uncertainty"]["k"] > 0 and " ± " in x["title"] and "held out" in x["reason"]
    assert "-     value: 2          # what we believe" in x["edit"]["diff"]
    assert f"+     value: {ye.number(x['parameters']['k'])}          # what we believe" in x["edit"]["diff"]
    assert pr.pending(p) == [pr.stored(p)[x["id"]]]


def test_accepting_writes_only_the_value_keeps_the_comments_and_records_the_change(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    [x] = pr.make(p, snap)
    before = (tmp_path / "ergostat.yaml").read_text()
    got = pr.accept(p, x["id"][:5], snap)
    after = (tmp_path / "ergostat.yaml").read_text()
    new = ye.number(x["parameters"]["k"])
    assert after == before.replace("value: 2          # what we believe", f"value: {new}          # what we believe")
    assert got["status"] == "accepted" and got["applied"]["version_before"] != got["applied"]["version_after"]
    assert got["applied"]["fit_after"]["nmse"] < got["applied"]["fit_before"]["nmse"]
    [ev] = pr.accepted(p)
    assert ev["proposal"] == x["id"] and ev["fit_after"] == got["applied"]["fit_after"]
    assert len(ft.versions(p)) == 2                                         # the fit of each version, before and after
    assert pr.pending(p) == [] and pr.make(p, snap) == []                    # it fits as written now
    with pytest.raises(pr.ProposalError, match="accepted already"):
        pr.accept(p, x["id"], snap)


def test_a_dismissed_proposal_is_not_made_again(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    [x] = pr.make(p, snap)
    pr.dismiss(p, x["id"])
    assert pr.make(p, snap) == [] and pr.stored(p)[x["id"]]["status"] == "dismissed"
    assert p.events.query(n=1, type="ergostat.model-change.dismissed")[-1]["source"] == "owner"


def test_a_file_changed_since_is_never_written_over(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    [x] = pr.make(p, snap)
    f = tmp_path / "ergostat.yaml"
    f.write_text(f.read_text().replace("# what we believe", "# what I believe"))
    with pytest.raises(pr.ProposalError, match="changed since"):
        pr.accept(p, x["id"], snap)
    assert "# what I believe" in f.read_text()


def test_an_edit_that_would_break_the_model_is_put_back(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    [x] = pr.make(p, snap)
    props = pr.stored(p)
    props[x["id"]]["edit"]["files"][0]["hunks"][0]["new"] = ["    value: [oops"]
    pr.save(p, props)
    f = tmp_path / "ergostat.yaml"
    before = f.read_text()
    with pytest.raises(pr.ProposalError, match="errors"):
        pr.accept(p, x["id"], snap)
    assert f.read_text() == before


def test_a_flow_with_causes_and_no_equation_is_proposed_one_by_least_squares(tmp_path):
    text = QUEUE.replace("    equation: k * stock.queue\n", "    sensor:\n      manual: true\n")
    write(tmp_path, text.replace("    estimate: true\n", ""))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    q = 0.0
    for i in range(121):
        t = now - 3600 + i * 30
        a = 10 + 5 * ((i // 20) % 2)
        for name, v in (("queue.main", q), ("arrivals.main", a), ("served.main", 3 * q)):
            p.measurements.add(f"sensor/{name}", v, at=t)
        for _ in range(30):
            q += (a - 3 * q) / 3600
    snap = {"at": now, "window": 3600.0, "starts": now - 3600}
    got = [x for x in pr.make(p, snap) if x["kind"] == "equation"]
    # an outflow: first order in its stock, written with the time things stay (Sterman ch. 13.3), never a rate constant
    assert len(got) == 1 and got[0]["equation"] == "stock.queue / time-in-queue"
    assert got[0]["parameters"]["time-in-queue"]["value"] == pytest.approx(1 / 3, rel=0.02)
    assert got[0]["parameters"]["time-in-queue"]["unit"] == "h" and "R² = 1 − SSE/SST" in got[0]["reason"]
    pr.accept(p, got[0]["id"], snap)
    spec = sp.load(tmp_path / "ergostat.yaml")
    assert spec.flows["served"].equation.text == "stock.queue / time-in-queue"
    assert spec.parameters["time-in-queue"].estimate and spec.parameters["time-in-queue"].duration
    assert spec.parameters["time-in-queue"].value == pytest.approx(1 / 3, rel=0.02)
    assert "# the queue drains at k an hour" in (tmp_path / "ergostat.yaml").read_text()


def test_yaml_edits_keep_everything_else_as_it_was(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("a:\n  k: {value: 2, unit: h}   # inline\n  b:\n    x: 1\n\n  c: 3\nparameters:\n  z:\n    value: 1\n")
    e = ye.set_value(f, 2, "value", "2.5")
    assert e.hunks[0].new == ["  k: {value: 2.5, unit: h}   # inline"]
    e = ye.add_key(f, 3, "equation", "k * 2")
    assert ye.apply(e).split("\n")[4] == "    equation: k * 2"
    e = ye.add_entries(f, "parameters", [["  y:", "    value: 4"]])
    assert ye.apply(e).endswith("  z:\n    value: 1\n  y:\n    value: 4\n")
    g = tmp_path / "y.yaml"
    g.write_text("flows:\n  a:\n    to: b\n")
    assert ye.apply(ye.add_entries(g, "parameters", [["  y: 1"]])) == "flows:\n  a:\n    to: b\n\nparameters:\n  y: 1\n"
    assert ye.number(0.000012345) == "0.00001234" and ye.number(3.0) == "3" and float(ye.number(1234567.0)) == 1235000


# ---- the command line and the page's API

def test_the_command_line_fits_proposes_and_accepts(tmp_path, capsys):
    from ergostat.cli import main
    p, _ = queue_project(tmp_path, k_true=3.0)
    assert main(["-C", str(tmp_path), "fit"]) == 0
    out = capsys.readouterr().out
    assert "queue" in out and "U_M" in out and "total" in out
    assert main(["-C", str(tmp_path), "proposals", "--json"]) == 0
    [x] = json.loads(capsys.readouterr().out)
    assert main(["-C", str(tmp_path), "accept", x["id"]]) == 0
    assert "accepted" in capsys.readouterr().out and re.search(r"value: (3|2\.99\d*|3\.0\d*) ", (tmp_path / "ergostat.yaml").read_text())
    assert main(["-C", str(tmp_path), "accept", "nothing"]) == 2


def test_the_page_gets_the_fit_the_replay_and_an_equations_numbers(tmp_path):
    from ergostat.web.server import Live, api
    p, _ = queue_project(tmp_path, k_true=3.0)
    live = Live(p)
    q = {"since": ["1h"]}
    fit = api(live, "fit", q)
    assert fit["stocks"][0]["name"] == "queue" and {"r2", "mape", "um", "us", "uc", "partial"} <= set(fit["words"])
    # the Model page's "What's available": where k's what-if and calibrations are, and whether the record is long
    # enough for a proposal (two hours of a queue whose time constant is 20 minutes: three of it, and 40 points)
    ready = fit["readiness"]["k"]
    assert ready["parts"] == ["flow.served"] and ready["points_needed"] == 40
    assert ready["needs"] == pytest.approx(3 * ready["slowest"]) and ready["span"] >= ready["needs"] and ready["points"] >= 40
    got = api(live, "series", {**q, "refs": ["stock.queue"], "strip": ["1"], "replay": ["1"]})
    s = {x["ref"]: x for x in got["series"]}
    assert len(s["stock.queue"]["replay"]) == got["points"] and s["flow.served"]["modelled"] == "equation"
    assert "replay" not in s["flow.arrivals"] and len(got["projection_times"]) == len(s["stock.queue"]["projection"])
    part = api(live, "part/flow/served", q)["numbers"]
    assert part["equation_text"] == "k * stock.queue" and part["equation_tree"]["op"] == "*"
    assert part["parameters"][0]["name"] == "k" and part["parameters"][0]["provenance"] == "declared"
    from ergostat.web.numbers_api import post
    code, made = post(live, "estimate", 3600.0)
    assert code == 200 and len(made["proposals"]) == 1
    assert api(live, "part/flow/served", q)["numbers"]["parameters"][0]["estimated"]["value"] == pytest.approx(3, rel=0.02)
    assert len(api(live, "part/flow/served", q)["numbers"]["proposals"]) == 1
    code, got = post(live, f"proposals/{made['proposals'][0]['id']}/accept", 3600.0)
    assert code == 200 and got["status"] == "accepted"
    assert post(live, "proposals/zzz/accept", 3600.0)[0] == 409


def test_a_projection_holds_its_inputs_or_carries_them_on_along_their_trend(tmp_path):
    write(tmp_path, QUEUE)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(121):
        p.measurements.add("sensor/queue.main", 5.0, at=now - 3600 + i * 30)
        p.measurements.add("sensor/arrivals.main", 10 + i * 0.1, at=now - 3600 + i * 30)      # rising, 12 an hour
    data = sim.measured(p, sim.Grid(now - 3600, now, 120))
    run = sim.replay(p.model.spec, data)
    held = sim.project(p.model.spec, data, run, 1800)
    trend = sim.project(p.model.spec, data, run, 1800, inputs="trend")
    assert trend.values["stock.queue"][-1] > held.values["stock.queue"][-1]
    assert held.notes == ["open loop: inputs held where they were, controllers held"] and "trend" in trend.notes[0]
    assert len(held.times) == 60 and held.times[0] > now


def test_a_flow_never_measured_is_taken_as_0_in_the_replay_and_the_projection(tmp_path):
    text = QUEUE + "  leak:\n    from: queue\n"
    p, snap = queue_project(tmp_path, text=text)
    data, run, _ = ft.compute(p, snap)
    assert "flow.leak was never measured in the window: taken as 0" in run.notes
    proj = sim.project(p.model.spec, data, run, 600)
    assert all(v is not None for v in proj.values["stock.queue"])


def test_a_duration_estimated_is_written_back_as_a_duration(tmp_path):
    text = QUEUE.replace("  k:\n    value: 2          # what we believe\n    unit: 1/h\n",
                         "  k:\n    value: 30m        # a time to drain\n").replace("k * stock.queue", "stock.queue / k")
    p, snap = queue_project(tmp_path, k_true=3.0, text=text)
    [x] = pr.make(p, snap)
    assert re.fullmatch(r"k: 30m → (19\.9\d*|20(\.0\d*)?)m ± [\d.]+s", x["title"]), x["title"]
    pr.accept(p, x["id"], snap)
    assert sp.load(tmp_path / "ergostat.yaml").parameters["k"].value == pytest.approx(1 / 3, rel=0.02)
    assert re.search(r"    value: [\d.]+m        # a time to drain", (tmp_path / "ergostat.yaml").read_text())
    assert ye.duration(0.003438) == "12.38s" and ye.duration(2.25) == "2.25h"


def test_only_the_page_itself_may_write_not_a_page_on_another_name(tmp_path):
    """DNS rebinding: a page on another site whose name points at 127.0.0.1 is same-origin to the
    browser and can set any header, so the server checks the Host it was addressed by, the Origin, and
    a token only the page it served carries."""
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from ergostat.web.server import handler
    p, _ = queue_project(tmp_path, k_true=3.0)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(p))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def ask(method, path, headers):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest(method, path, skip_host=True)
        for k, v in headers.items():
            c.putheader(k, v)
        c.putheader("Content-Length", "0")
        c.endheaders()
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body
    try:
        mine = {"Host": f"127.0.0.1:{port}"}
        code, page = ask("GET", "/", mine)
        token = re.search(rb'name="ergostat-token" content="([^"]+)"', page).group(1).decode()
        assert code == 200 and token
        assert ask("GET", "/api/status", {"Host": f"attacker.example:{port}"})[0] == 403
        assert ask("POST", "/api/proposals/zzz/accept", {"Host": f"attacker.example:{port}", "X-Ergostat-Token": token})[0] == 403
        assert ask("POST", "/api/proposals/zzz/accept", mine)[0] == 403                      # no token
        assert ask("POST", "/api/proposals/zzz/accept", {**mine, "X-Ergostat-Token": "guess"})[0] == 403
        assert ask("POST", "/api/proposals/zzz/accept", {**mine, "X-Ergostat-Token": token,
                                                          "Origin": "http://attacker.example"})[0] == 403
        assert ask("POST", "/api/proposals/zzz/accept", {**mine, "X-Ergostat-Token": token,
                                                          "Sec-Fetch-Site": "cross-site"})[0] == 403
        assert ask("POST", "/api/proposals/zzz/accept", {**mine, "X-Ergostat-Token": token,
                                                          "Origin": f"http://127.0.0.1:{port}"})[0] == 409
        assert ask("POST", "/api/proposals/zzz/accept", {"Host": f"localhost:{port}", "X-Ergostat-Token": token})[0] == 409
    finally:
        srv.shutdown()
        srv.server_close()


# ---- the integrator follows the model's dynamics, not the units its parameters are written in

STIFF = """\
name: s
parameters:
  workdays-per-hour:
    value: 60
    unit: workdays/h
  ramp-time-live:
    value: 0.41
    unit: workdays
stocks:
  live:
    unit: ramps
    sensor:
      manual: true
flows:
  went-ahead:
    to: live
    sensor:
      manual: true
  ended:
    from: live
    driven-by: +stock.live
    equation: workdays-per-hour * stock.live / ramp-time-live
"""


@pytest.mark.parametrize("hours", [24, 168])
def test_a_time_constant_in_workdays_sets_the_step_and_the_replay_stays_at_its_equilibrium(tmp_path, hours):
    """The reviewer's case: 60 ramps an hour into a stock that drains in 0.41 working days (24.6 s).
    A step from units alone (only "h") went 1 → 1473 → 3.7e6; the step from the dynamics holds 0.41."""
    write(tmp_path, STIFF)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    span = hours * 3600.0
    for i in range(int(span // 600) + 1):
        t = now - span + i * 600
        p.measurements.add("sensor/live.main", 1.0 if i == 0 else 0.41, at=t)
        p.measurements.add("sensor/went-ahead.main", 60.0, at=t)
    _, _, got = ft.compute(p, {"at": now})                    # the fit: on the reference window, the last day
    assert got["total"] is not None and got["stocks"]["stock.live"]["rmse"] < 0.05
    run = sim.replay(p.model.spec, sim.measured(p, sim.Grid(now - span, now, 120)))      # the page's window, for its charts
    vals = [v for v in run.values["stock.live"] if v is not None]
    assert run.valid and max(vals) < 1.01 and vals[-1] == pytest.approx(0.41, rel=0.01), (vals[:5], run.notes)
    assert run.time_constants["stock.live"] == pytest.approx(0.41 / 60, rel=0.01)       # 24.6 s, from the dynamics
    if hours == 168:      # buckets of 84 minutes cannot follow 24.6 s: said, and integrated implicitly
        assert any("settled at once" in n for n in run.notes)


def test_a_replay_that_blows_up_is_clamped_noted_and_not_valid(tmp_path):
    text = STIFF.replace("workdays-per-hour * stock.live / ramp-time-live", "0 - workdays-per-hour * stock.live * 1000")
    write(tmp_path, text.replace("driven-by: +stock.live", "driven-by: -stock.live"))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i in range(121):
        p.measurements.add("sensor/live.main", 1.0, at=now - 3600 + i * 30)
        p.measurements.add("sensor/went-ahead.main", 60.0, at=now - 3600 + i * 30)
    _, run, got = ft.compute(p, {"at": now})
    assert not run.valid and any("clamped" in n for n in run.invalid)
    assert got["total"] is None and got["invalid"]


def test_a_division_by_zero_is_counted_and_said_and_zidz_is_the_way_to_mean_it(tmp_path):
    text = QUEUE.replace("equation: k * stock.queue", "equation: k * stock.queue / stock.queue")
    p, snap = queue_project(tmp_path, k_true=2.0, text=text)
    _, run, _ = ft.compute(p, snap)
    assert any(n.startswith("flow.served: divided by 0") and "ZIDZ" in n for n in run.notes), run.notes
    text = QUEUE.replace("equation: k * stock.queue", "equation: k * ZIDZ(stock.queue, stock.queue)")
    (tmp_path / "b").mkdir()
    p, snap = queue_project(tmp_path / "b", k_true=2.0, text=text)
    _, run, _ = ft.compute(p, snap)
    assert not any("divided by 0" in n for n in run.notes)
    assert run_eq("XIDZ(1, 0, 7)", {}) == 7 and run_eq("ZIDZ(6, 3)", {}) == 2


@pytest.mark.parametrize("hours", [24, 168])
def test_the_job_replays_at_a_day_and_a_week_without_blowing_up(tmp_path, hours):
    """The-job's model as written, on a record of ramps going ahead and breaking or proving fine as its
    world makes them (world/traffic.py)."""
    import random
    import shutil
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "examples" / "the-job"
    shutil.copytree(src, tmp_path / "job", ignore=shutil.ignore_patterns("run", "__pycache__"))
    p = Project(mdl.load(tmp_path / "job"))
    rnd = random.Random(4)
    now = time.time()
    span, day = hours * 3600.0, 60.0
    per_hour = 20 if hours == 24 else 3
    live = []
    t = now - span
    i = 0
    while t < now:
        i += 1
        rid = f"ramp/{i}"
        p.events.add("ramp.requested", item=rid, at=t)
        p.events.add("ramp.went-ahead", item=rid, at=t + 1)
        if rnd.random() < 0.45:
            end, what = t + 1 + day * rnd.uniform(0.1, 0.5), "ramp.broke"
        else:
            end, what = t + 1 + day * 0.5, "ramp.proved-fine"
        if end < now:
            p.events.add(what, item=rid, at=end)
        live.append((t + 1, end))
        t += rnd.expovariate(per_hour / 3600.0)
    for k in range(int(span // 300) + 1):
        at = now - span + k * 300
        p.measurements.add("sensor/unreviewed-ramps-live.main", float(sum(1 for a, b in live if a <= at < b)), at=at)
    data = sim.measured(p, sim.Grid(now - span, now, 120))     # the page's window
    run = sim.replay(p.model.spec, data)
    vals = [v for v in run.values["stock.unreviewed-ramps-live"] if v is not None]
    assert run.valid, run.invalid
    assert vals and max(vals) < 20, max(vals)                    # not 2.6e10
    meas = [v for v in data.values["stock.unreviewed-ramps-live"] if v is not None]
    assert abs(sum(vals) / len(vals) - sum(meas) / len(meas)) < 0.1    # the delays hand on what they take in
    _, ref, got = ft.compute(p, {"at": now})                    # the fit, on the reference window
    assert ref.valid and got["partial"]["flow.ramps-broke"]["n"] >= 10
    assert abs(got["partial"]["flow.ramps-broke"]["um"]) < 0.2   # its delay's output is not biased


# ---- one accounting basis: the replay of what was counted is the record

TICKETS = """\
name: t
items:
  ticket:
    id: ticket/*
    states: [open, done]
    on:
      ticket.done: done
stocks:
  open-tickets:
    unit: tickets
    sensor:
      manual: true
  waiting:
    unit: tickets
    sensor:
      manual: true
flows:
  opened:
    to: open-tickets
    sensor:
      items: ticket
      entering: open
      over: 10m
  closed:
    from: open-tickets
    sensor:
      items: ticket
      entering: done
      over: 10m
  queued:
    to: waiting
    sensor:
      manual: true
  picked:
    from: waiting
    driven-by: +stock.waiting
    equation: stock.waiting / time-waiting
parameters:
  time-waiting:
    value: 6m
"""


def tickets_project(tmp_path, minutes=60, seed=3):
    import random
    write(tmp_path, TICKETS)
    p = Project(mdl.load(tmp_path))
    rnd = random.Random(seed)
    now = time.time()
    since = now - minutes * 60
    life = []
    t = since - 120                                 # some opened before the record's first reading
    i = 0
    while t < now:
        i += 1
        end = t + rnd.uniform(30, 600)
        p.events.add("ticket.opened", item=f"ticket/{i}", at=t)
        if end < now:
            p.events.add("ticket.done", item=f"ticket/{i}", at=end)
        life.append((t, end))
        t += rnd.expovariate(1 / 40)
    for k in range(minutes * 3 + 1):                # a reading every 20 s, the first 7 s in
        at = since + 7 + k * 20
        if at <= now:
            p.measurements.add("sensor/open-tickets.main", float(sum(1 for a, b in life if a <= at < b)), at=at)
    return p, {"at": now, "window": minutes * 60.0, "starts": since}


def test_a_stock_whose_flows_are_all_counted_replays_its_own_readings(tmp_path):
    """Homer 2012: drive data aligned with the stock. Started at its first reading, driven by what
    moved after it, a stock whose flows are all counted replays with no error at all, whatever window."""
    p, snap = tickets_project(tmp_path)
    for n in (120, 37):
        data = sim.measured(p, sim.Grid(snap["at"] - 3600, snap["at"], n))
        run = sim.replay(p.model.spec, data)
        got = ft.compare(p.model.spec, data, run)
        s = got["accounting"]["stock.open-tickets"]
        assert s.get("exact") or s["rmse"] < 1e-9, s                 # every reading, to the ticket
        assert "stock.open-tickets" not in got["stocks"]          # it tests no equation: accounting, not the model's fit
        first_t, first_v = data.started["stock.open-tickets"]
        moved = data.counted["flow.opened"].between(first_t, snap["at"]) - data.counted["flow.closed"].between(first_t, snap["at"])
        assert run.state["open-tickets"] == pytest.approx(first_v + moved)      # what the residual calls explained
    assert data.how["flow.opened"].startswith("items entering open, counted as they moved")


def test_the_fit_is_of_the_reference_window_never_the_pages(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    a = ft.compute(p, {**snap, "window": 600.0})[2]
    b = ft.compute(p, {**snap, "window": 7 * 24 * 3600.0})[2]
    assert a["stocks"] == b["stocks"] and a["span"] == pytest.approx(7200, abs=31)


def test_a_rate_a_sensor_averages_is_compared_with_the_models_own_average(tmp_path):
    """Ljung ch. 4: the predictor includes the measurement. A sensor that reads the last ten minutes'
    average of an equation that is exactly right fits it once the model is read the same way."""
    text = QUEUE.replace("    equation: k * stock.queue\n",
                         "    equation: k * stock.queue\n    sensor:\n      run: x\n      averages: 10m\n")
    p, snap = queue_project(tmp_path, k_true=2.0, text=text, minutes=120)
    now = snap["at"]
    pts = p.measurements.range("sensor/queue.main", now - 7200, now)
    for t, _ in pts:
        if t < now - 7200 + 600:
            continue
        w = [v for u, v in pts if t - 600 < u <= t]
        p.measurements.add("sensor/served.main", 2.0 * sum(w) / len(w), at=t)
    _, _, got = ft.compute(p, snap)
    lagged = got["partial"]["flow.served"]
    assert lagged["r2"] > 0.98 and abs(lagged["mean_replay"] - lagged["mean_measured"]) < 0.05 * lagged["mean_measured"]
    plain = QUEUE.replace("    equation: k * stock.queue\n", "    equation: k * stock.queue\n    sensor:\n      run: x\n")
    write(tmp_path, plain)
    p.model = mdl.load(tmp_path)
    _, _, raw = ft.compute(p, snap)
    assert raw["partial"]["flow.served"]["r2"] < lagged["r2"]       # read as instantaneous, the same record fits worse


def test_the_partial_test_and_the_replay_are_each_shown_as_themselves(tmp_path):
    text = QUEUE.replace("    equation: k * stock.queue\n", "    equation: k * stock.queue\n    sensor:\n      manual: true\n")
    p, snap = queue_project(tmp_path, k_true=3.0, text=text)
    now = snap["at"]
    for t, q in p.measurements.range("sensor/queue.main", now - 7200, now):
        p.measurements.add("sensor/served.main", 3.0 * q, at=t)
    _, _, got = ft.compute(p, snap)
    part, rep = got["partial"]["flow.served"], got["equations"]["flow.served"]
    assert part["um"] > 0.5 and part["mean_replay"] < part["mean_measured"]      # k = 2 on the measured queue: too little
    assert rep["mean_replay"] != pytest.approx(part["mean_replay"], rel=0.01)    # on a replayed queue, which has drifted


# ---- a proposal only where the record supports it

def test_no_proposal_from_too_short_a_record_for_the_time_constant_it_touches(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0, minutes=20)              # 20 minutes; the queue's time constant is 30
    assert pr.make(p, snap) == []
    e = es.load(p, p.model.spec)["k"]
    assert e["refused"].startswith("held, inconclusive: too little record") and "under 3 of the slowest" in e["refused"]
    assert "more record" in e["refused"]                                  # and how much more it needs


def test_no_proposal_when_the_estimate_is_within_its_error_of_the_value_written(tmp_path):
    p, snap = queue_project(tmp_path, k_true=2.0)                          # the model is right
    assert pr.make(p, snap) == []
    assert "two standard errors" in es.load(p, p.model.spec)["k"]["refused"] or \
        "less than 2%" in es.load(p, p.model.spec)["k"]["refused"]


def test_an_estimate_at_its_bound_is_refused_as_a_question_of_structure():
    e = {"value": 2000.0, "window": 7200, "slowest": 0.5, "at_bound": True, "identifiable": True, "se": 0.1, "logged": True,
         "n": 96}
    assert "structure" in es.judged(e, 2.0)
    e |= {"at_bound": False, "identifiable": False}
    assert "does not tell it apart" in es.judged(e, 2.0)
    e |= {"identifiable": True, "held_before": 1.0, "held_after": 1.2}
    assert "held out" in es.judged(e, 2.0)


def test_two_parameters_fitted_together_carry_their_correlation(tmp_path):
    text = QUEUE.replace("  k:\n", "  k0:\n    value: 1\n    unit: jobs/h\n    estimate: true\n  k:\n").replace(
        "equation: k * stock.queue", "equation: k0 + k * stock.queue")
    p, snap = queue_project(tmp_path, k_true=3.0, text=text)
    got = es.estimate(p, snap)
    assert got["k"]["with"] == ["k0"] and "k0" in got["k"]["corr"] and -1 <= got["k"]["corr"]["k0"] <= 1


def _equation_project(tmp_path, text, rows):
    write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for i, row in enumerate(rows):
        for name, v in row.items():
            p.measurements.add(f"sensor/{name}.main", v, at=now - 3600 + i * 30)
    return p, {"at": now, "window": 3600.0, "starts": now - 3600}


def test_an_outflow_that_does_not_name_its_stock_is_not_given_an_equation(tmp_path):
    text = QUEUE.replace("    driven-by: +stock.queue\n    equation: k * stock.queue\n",
                         "    driven-by: +flow.arrivals\n    sensor:\n      manual: true\n").replace("    estimate: true\n", "")
    rows = [{"queue": 5.0, "arrivals": 10 + i % 7, "served": 10 + i % 7} for i in range(121)]
    p, snap = _equation_project(tmp_path, text, rows)
    assert [x for x in pr.make(p, snap) if x["kind"] == "equation"] == []


def test_a_one_way_inflow_never_gets_a_negative_constant_and_never_runs_backwards(tmp_path):
    text = """\
name: e
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
auxiliaries:
  load:
    unit: jobs
    exogenous: true
    sensor:
      manual: true
flows:
  arrivals:
    to: queue
    driven-by: +auxiliary.load
    sensor:
      manual: true
  served:
    from: queue
    sensor:
      manual: true
"""
    rows = [{"queue": 5.0, "load": 4 + i % 9, "arrivals": max(0.0, 3 * (4 + i % 9) - 14), "served": 1.0} for i in range(121)]
    p, snap = _equation_project(tmp_path, text, rows)
    [x] = [x for x in pr.make(p, snap) if x["kind"] == "equation"]
    assert "arrivals-base" not in x["parameters"]                       # fitted through 0, not with a constant below it
    assert x["equation"].startswith("MAX(0, ") or all(v["value"] >= 0 for v in x["parameters"].values())
    r2 = float(re.search(r"explain (\d+)%", x["reason"]).group(1)) / 100
    ys = [r["arrivals"] for r in rows]
    k = x["parameters"]["arrivals-per-load"]["value"]
    fitted = [k * r["load"] for r in rows]
    assert r2 == pytest.approx(es.r_squared(fitted, ys), abs=0.01)       # 1 − SSE/SST, not the squared correlation


def test_the_projection_is_open_loop_and_leaves_out_what_a_controller_moves(tmp_path):
    text = QUEUE + """\
  drained:
    from: queue
goals:
  short:
    stock: queue
    hold: "<= 3"
blocks:
  drainer:
    type: program
    run: "true"
    goal: short
    out: flow.drained
"""
    p, snap = queue_project(tmp_path, k_true=2.0, text=text)
    data = sim.measured(p, sim.Grid(snap["at"] - 3600, snap["at"], 120))
    run = sim.replay(p.model.spec, data)
    proj = sim.project(p.model.spec, data, run, 1800)
    assert proj.notes[0].startswith("open loop") and "controllers held" in proj.notes[0]
    assert all(v is None for v in proj.values["stock.queue"]) and all(v is None for v in proj.values["flow.served"])
    assert "left out downstream of a controller's flow" in proj.notes[1]


def test_the_residuals_and_the_replay_count_on_one_basis(tmp_path):
    """The replay of a stock whose flows are all counted and the residual's 'explained' agree: both are
    what moved between its first and last readings, not the trailing rates its sensors report."""
    from ergostat import state
    p, snap = tickets_project(tmp_path)
    for name in ("opened", "closed"):                       # readings of a trailing count, as the runner records them
        for k in range(181):
            at = snap["at"] - 3600 + k * 20
            p.measurements.add(f"sensor/{name}.main", 6.0, at=at)
    st_ = state.snapshot(p, 3600, snap["at"])
    r = st_["residuals"]["open-tickets"]
    data = sim.measured(p, sim.Grid(snap["at"] - 3600, snap["at"], 120))
    run = sim.replay(p.model.spec, data)
    t0, v0 = data.started["stock.open-tickets"]
    assert r["explained"] == pytest.approx(run.state["open-tickets"] - v0, abs=1e-9)
    assert abs(r["unexplained"]) < 1e-9


def test_no_proposal_from_fewer_points_than_a_proposal_needs_or_errors_that_run_together():
    e = {"value": 3.0, "window": 7200, "slowest": 0.5, "at_bound": False, "identifiable": True, "se": 0.01, "logged": True,
         "n": 24, "after": 0.5, "n_eff": 30, "held_before": 1.0, "held_after": 0.5}
    assert "24 points fitted, under 40" in es.judged(e, 2.0)
    e |= {"n": 96, "n_eff": 3, "rho": 0.9}
    assert "independent" in es.judged(e, 2.0)                  # a systematic error left, and few independent points
    e |= {"after": 1e-6}
    assert es.judged(e, 2.0) is None                           # it fits exactly: what is left is not evidence against it


def test_a_stock_that_only_integrates_is_judged_by_the_time_things_stay_in_it(tmp_path):
    p, snap = tickets_project(tmp_path)
    data = sim.measured(p, sim.Grid(snap["at"] - 3600, snap["at"], 120))
    t = es.residence(p.model.spec, data, "open-tickets")
    assert t is not None and 30 / 3600 < t < 600 / 3600         # tickets stay half a minute to ten minutes
