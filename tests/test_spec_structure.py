"""The structure checks `ergostat check` makes as system dynamics would (SPEC §12; Sterman, *Business
Dynamics*, ch. 21): a rate driven by a rate (a missing stock), a stock nothing drains, units a link
joins with nothing to convert them, an outflow that ignores its stock, an auxiliary with no causes.
Each names its fix in plain words and the YAML that writes it."""

import textwrap

from ergostat.spec import read
from ergostat.spec.findings import base_unit

NEW = ("rate-driven-by-rate", "units-mismatch", "outflow-ignores-stock", "stock-without-outflow", "auxiliary-without-causes")


def check(tmp_path, text):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    s, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems
    return s, {(p.code, p.about): p.message for p in problems if p.code in NEW}


RAMPS = """
stocks:
  ramps-waiting: {unit: ramps}
  alerts-open: {unit: alerts}
flows:
  ramps-went-ahead:
    from: ramps-waiting
    driven-by: +stock.ramps-waiting
  alerts-fired:
    to: alerts-open
    driven-by: {LINK}
  alerts-closed:
    from: alerts-open
    driven-by: +stock.alerts-open
"""


def test_a_rate_driven_by_a_rate_is_a_missing_stock_and_says_how_to_write_it(tmp_path):
    _, found = check(tmp_path, RAMPS.replace("{LINK}", "+flow.ramps-went-ahead"))
    msg = found[("rate-driven-by-rate", "flow.alerts-fired")]
    assert "goes through a stock" in msg and "driven-by: +stock." in msg
    assert "{cause: +flow.ramps-went-ahead, instant: true}" in msg          # the way to say it really is immediate
    assert ("units-mismatch", "flow.alerts-fired") in found                 # alerts following ramps, nothing converting


def test_a_link_declared_instant_is_not_a_missing_stock_but_still_needs_its_units_converted(tmp_path):
    _, found = check(tmp_path, RAMPS.replace("{LINK}", "{cause: +flow.ramps-went-ahead, instant: true}"))
    assert ("rate-driven-by-rate", "flow.alerts-fired") not in found
    msg = found[("units-mismatch", "flow.alerts-fired")]
    assert "auxiliaries: {alerts-per-ramp: {unit: alerts/ramp}}" in msg and "+auxiliary.alerts-per-ramp" in msg


def test_a_converting_auxiliary_or_the_stock_it_takes_from_silences_units(tmp_path):
    s, found = check(tmp_path, RAMPS.replace("{LINK}", "[{cause: +flow.ramps-went-ahead, instant: true}, +auxiliary.alerts-per-ramp]")
                     + "auxiliaries:\n  alerts-per-ramp: {unit: alerts/ramp, exogenous: true}\n")
    assert not found, found
    assert s.flows["alerts-fired"].instant == {"flow.ramps-went-ahead"}
    assert s.flows["alerts-fired"].polarity == {"flow.ramps-went-ahead": 1, "auxiliary.alerts-per-ramp": 1}


def test_a_flow_through_the_stock_is_quiet(tmp_path):
    """The fix the finding asks for: the cause accumulates in a stock, and the effect follows it."""
    _, found = check(tmp_path, """
stocks:
  ramps-live: {unit: ramps}
  alerts-open: {unit: alerts}
flows:
  ramps-went-ahead: {to: ramps-live}
  ramps-broke: {from: ramps-live, driven-by: +stock.ramps-live}
  alerts-fired: {to: alerts-open, driven-by: +stock.ramps-live}
  alerts-closed: {from: alerts-open, driven-by: +stock.alerts-open}
""")
    assert not found, found


def test_a_stock_nothing_drains_is_reported_unless_it_is_a_running_total(tmp_path):
    text = """
stocks:
  spent: {unit: USD{CUM}}
  setting: {unit: q}
flows:
  spending: {to: spent}
  steps: {to: setting, two-way: true}
"""
    _, found = check(tmp_path, text.replace("{CUM}", ""))
    msg = found[("stock-without-outflow", "stock.spent")]
    assert "can only grow" in msg and "from: spent" in msg and "cumulative: true" in msg
    assert ("stock-without-outflow", "stock.setting") not in found            # a two-way flow drains it as well
    s, found = check(tmp_path, text.replace("{CUM}", ", cumulative: true"))
    assert not found and s.stocks["spent"].cumulative


def test_an_outflow_that_ignores_its_stock_would_take_it_below_zero(tmp_path):
    text = """
stocks:
  bugs: {unit: bugs}
  done: {unit: tickets}
flows:
  deployed: {from: done}
  fixes:
    from: bugs
    driven-by: [{cause: +flow.deployed, instant: true}, +auxiliary.bugs-per-ticket{MORE}]
auxiliaries:
  bugs-per-ticket: {unit: bugs/ticket, exogenous: true}
  share-fixed: {unit: share, driven-by: +stock.bugs}
"""
    _, found = check(tmp_path, text.replace("{MORE}", ""))
    msg = found[("outflow-ignores-stock", "flow.fixes")]
    assert "below zero" in msg and "+stock.bugs" in msg
    _, found = check(tmp_path, text.replace("{MORE}", ", +auxiliary.share-fixed"))   # through an auxiliary of the stock
    assert ("outflow-ignores-stock", "flow.fixes") not in found


def test_an_auxiliary_with_no_causes_is_named_an_input_from_outside_or_given_them(tmp_path):
    _, found = check(tmp_path, """
stocks:
  queue: {unit: jobs}
flows:
  arrivals: {to: queue, driven-by: +auxiliary.price}
  served: {from: queue, driven-by: +stock.queue}
auxiliaries:
  price: {unit: USD}
""")
    msg = found[("auxiliary-without-causes", "auxiliary.price")]
    assert "exogenous: true" in msg and "driven-by:" in msg


def test_units_are_compared_as_counts_and_ratios_are_left_alone():
    assert base_unit("alerts") == base_unit("alert/h") == base_unit("alerts per hour") == "alert"
    assert base_unit("ops") == "ops" and base_unit("share") is None and base_unit("KB/MP") is None


def test_a_link_written_out_is_checked(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
stocks:
  a: {unit: x}
flows:
  f: {to: a}
  g: {from: a, driven-by: [{instant: true}, {cause: +flow.f, instant: yes-please, why: x}]}
"""))
    _, problems = read(tmp_path / "ergostat.yaml")
    codes = {p.code for p in problems if p.level == "error"}
    assert {"missing-key", "bad-bool", "unknown-key"} <= codes, problems


def test_the_examples_close_their_goals_with_no_structure_left_to_fix():
    """Every example's rate-to-rate links go through a stock or are declared instant, and its units convert."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "examples"
    for ex in sorted(p for p in root.iterdir() if (p / "ergostat.yaml").exists()):
        _, problems = read(ex / "ergostat.yaml")
        left = [(p.code, p.about) for p in problems if p.code in NEW]
        assert not left, (ex.name, left)


def test_the_schema_takes_a_link_written_out_and_a_running_total():
    import json
    from pathlib import Path

    import pytest
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((Path(__file__).resolve().parent.parent / "schema/ergostat.schema.json").read_text())
    v = jsonschema.Draft202012Validator(schema)
    good = {"stocks": {"spent": {"unit": "USD", "cumulative": True}},
            "flows": {"spending": {"to": "spent", "driven-by": ["+stock.spent", {"cause": "+flow.x", "instant": True}]}}}
    assert not list(v.iter_errors(good))
    bad = {"flows": {"spending": {"to": "spent", "driven-by": [{"instant": True}]}}}
    assert list(v.iter_errors(bad))
