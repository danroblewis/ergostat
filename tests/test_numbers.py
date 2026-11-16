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


def queue_project(tmp_path, k_true: float = 3.0, text: str = QUEUE, minutes: int = 60):
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
    text = QUEUE.replace("unit: 1/h\n", "unit: 1/day\n") + """\
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
    assert "comes out in day^-1·job" in said["equation-units"] or "job/day" in said["equation-units"]
    assert "size-unknown" in said and "other" in said["size-unknown"]
    assert "equation-not-drawn" in said and "stock.queue" in said["equation-not-drawn"]
    assert "parameter-unknown" in said and "lost" in said["parameter-unknown"]
    assert "auxiliary-without-causes" not in codes(probs)            # its equation is its cause


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
    assert s["r2"] > 0.999 and s["mape"] < 0.02, s
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
    assert got["n"] > 100 and got["fitted_to"] == ["stock.queue"]
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
    assert x["fit_after"]["total"]["mape"] < x["fit_before"]["total"]["mape"]
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
    assert got["applied"]["fit_after"]["mape"] < got["applied"]["fit_before"]["mape"]
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
    assert p.events.query(n=1, type="model.dismissed")


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
    assert len(got) == 1 and got[0]["equation"] == "served-per-queue * stock.queue"    # an outflow: no constant term
    assert got[0]["parameters"]["served-per-queue"]["value"] == pytest.approx(3.0, rel=0.02)
    assert got[0]["parameters"]["served-per-queue"]["unit"] == "1/h"
    pr.accept(p, got[0]["id"], snap)
    spec = sp.load(tmp_path / "ergostat.yaml")
    assert spec.flows["served"].equation.text == "served-per-queue * stock.queue"
    assert spec.parameters["served-per-queue"].estimate and spec.parameters["served-per-queue"].unit == "1/h"
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
    assert "accepted" in capsys.readouterr().out and "value: 3." in (tmp_path / "ergostat.yaml").read_text()
    assert main(["-C", str(tmp_path), "accept", "nothing"]) == 2


def test_the_page_gets_the_fit_the_replay_and_an_equations_numbers(tmp_path):
    from ergostat.web.server import Live, api
    p, _ = queue_project(tmp_path, k_true=3.0)
    live = Live(p)
    q = {"since": ["1h"]}
    fit = api(live, "fit", q)
    assert fit["stocks"][0]["name"] == "queue" and set(fit["words"]) == {"r2", "mape", "um", "us", "uc"}
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
    assert held.notes == ["inputs held where they were"] and "trend" in trend.notes[0]
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
    assert re.fullmatch(r"k: 30m → (19\.9\d*|20(\.0\d*)?)m", x["title"]), x["title"]
    pr.accept(p, x["id"], snap)
    assert sp.load(tmp_path / "ergostat.yaml").parameters["k"].value == pytest.approx(1 / 3, rel=0.02)
    assert re.search(r"    value: [\d.]+m        # a time to drain", (tmp_path / "ergostat.yaml").read_text())
    assert ye.duration(0.003438) == "12.38s" and ye.duration(2.25) == "2.25h"
