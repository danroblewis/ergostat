"""Rates as they read naturally (rates.py, SPEC §1a): the unit chosen by size, a flow's (or its stock's)
``rate-unit:`` over it, and nothing converted where a rate is kept: display only."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ergostat import blockdiagram as bd
from ergostat import rates
from ergostat.spec import SpecError, load

MODEL = """
stocks:
  queue:
    unit: jobs
    rate-unit: day
    sensor: {run: echo 3, every: 10s}
  inbox: {unit: mails, sensor: {run: echo 1, every: 10s}}
flows:
  arrivals: {to: queue, rate: 120}
  served: {from: queue, rate-unit: minute}
  mail: {to: inbox, rate: 0.5}
  read: {from: inbox, rate: 0.5, rate-unit: week}
"""


def spec_of(tmp_path: Path, text: str = MODEL):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return load(tmp_path / "ergostat.yaml")


@pytest.mark.parametrize("rate, unit", [(None, "hour"), (0, "hour"), (61, "minute"), (60, "hour"), (-500, "minute"),
                                        (1, "hour"), (0.99, "day"), (-0.2, "day"), (24, "hour")])
def test_the_unit_is_chosen_by_size(rate, unit):
    assert rates.choose(rate) == unit


def test_text_in_the_chosen_unit_and_the_override():
    assert rates.text(120, "alerts") == "2 alerts/min"
    assert rates.text(6, "alerts") == "6 alerts/h"
    assert rates.text(0.25, "outages") == "6 outages/day"
    assert rates.text(0.25) == "6/day"
    assert rates.text(None) == "?/h"
    assert rates.text(120, "alerts", "hour") == "120 alerts/h"
    assert rates.text(0.5, "", "week") == "84/week"
    assert rates.text(3, "", "bogus") == "3/h"                       # not a unit: chosen by size


def test_rate_unit_is_read_from_a_flow_and_from_its_stock_and_kept_per_hour(tmp_path):
    s = spec_of(tmp_path)
    assert (s.flows["served"].rate_unit, s.stocks["queue"].rate_unit, s.flows["arrivals"].rate_unit) == ("minute", "day", None)
    assert rates.override_of(s, "served") == "minute"                 # its own wins over its stock's
    assert rates.override_of(s, "arrivals") == "day"                  # its stock's, where it says none
    assert rates.override_of(s, "mail") is None
    assert rates.overrides(s) == {"arrivals": "day", "served": "minute", "read": "week"}
    assert s.flows["arrivals"].rate == 120                            # display only: the rate is kept per hour


def test_a_rate_unit_that_is_not_one_is_an_error(tmp_path):
    with pytest.raises(SpecError) as e:
        spec_of(tmp_path, "stocks:\n  q: {unit: x}\nflows:\n  in: {to: q, rate-unit: fortnight}\n")
    assert "rate-unit" in str(e.value) and "minute, hour, day, week" in str(e.value)


def test_the_block_diagram_says_a_rate_in_its_unit(tmp_path):
    s = spec_of(tmp_path)
    d = bd._Diagram(s, {"flows": {"mail": {"rate": 0.5}, "served": {"rate": 600}, "arrivals": {"rate": 30}}})
    assert d.now("flow.mail") == "12/day"
    assert d.now("flow.served") == "10/min"
    assert d.now("flow.arrivals") == "720/day"                        # its stock's rate-unit: day
