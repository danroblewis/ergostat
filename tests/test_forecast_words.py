"""A goal's forecast in words (numbers/forecast_words.py): the sentence forms, the odds as 'N in 10', the clock times,
and p, the runs and the horizon kept out of the sentence for its disclosure."""

from __future__ import annotations

import time

import pytest

from ergostat.numbers import forecast_words as fw

NOW = time.mktime((2026, 11, 22, 14, 0, 0, 0, 0, -1))      # 14:00 local


def got(p, horizon=480.0, made=100, invalid=0):
    return {"made": made, "invalid": invalid, "horizon": horizon, "stopped": None,
            "goals": {"users": {"p_off": p, "p_off_end": p[-1], "expected_off": 0.0}}}


@pytest.mark.parametrize("q, said", [(0.0, "under 1 in 10"), (0.04, "under 1 in 10"), (0.05, "1 in 10"), (0.14, "1 in 10"),
                                     (0.15, "2 in 10"), (0.25, "3 in 10"), (0.65, "7 in 10"), (0.94, "9 in 10"),
                                     (0.95, "over 9 in 10"), (1.0, "over 9 in 10")])
def test_odds_are_said_as_n_in_10_rounded_half_up(q, said):
    assert fw.odds(q) == said


def test_a_goal_likely_to_hold_says_for_how_long_and_how_likely():
    w = fw.said(got([0.02, 0.05, 0.07, 0.07]), "users", NOW)
    assert w["sentence"] == "Likely to stay within its bound for the next 8 minutes (about 9 in 10)"
    assert w["short"] == "within, 9 in 10"
    how = dict(w["how"])
    assert how["chance off at the horizon"] == "p≈0.07" and how["runs"] == "100" and how["horizon"] == "8 minutes, to 14:08"
    assert "p≈" not in w["sentence"] and "runs" not in w["sentence"] and "p≈0.07" in w["title"]


def test_a_goal_likely_to_cross_says_around_when():
    w = fw.said(got([0.1, 0.3, 0.6, 0.7], horizon=40 * 60), "users", NOW)
    assert w["sentence"] == "Likely to cross its bound around 14:30 (about 7 in 10)"
    assert w["short"] == "cross ~14:30, 7 in 10"


def test_a_goal_off_now_says_when_it_is_expected_back_or_that_it_stays_off():
    assert fw.said(got([0.9, 0.6, 0.3, 0.1], horizon=100 * 60), "users", NOW)["sentence"] == \
        "Expected back within its bound by 15:15"
    w = fw.said(got([0.9, 0.8, 0.8], horizon=3 * 3600, invalid=4), "users", NOW)
    assert w["sentence"] == "Likely to stay outside its bound for the next 3 hours (about 8 in 10)"
    assert dict(w["how"])["runs"] == "100 (4 not valid, counted as off)"


def test_a_goal_with_no_forecast_says_why():
    w = fw.said(None, "users", NOW)
    assert w == {"sentence": "No estimate: too little history", "short": "no estimate", "title": "too little history", "how": []}
    assert fw.said(got([0.1], made=0), "users", NOW, "no run could be made")["sentence"] == "No estimate: no run could be made"
    assert fw.said(got([0.1]), "other", NOW)["short"] == "no estimate"


def test_a_clock_time_on_another_day_names_the_day():
    assert fw.clock(NOW + 86400, NOW).endswith(" 14:00") and fw.clock(NOW + 86400, NOW) != "14:00"
    assert fw.span(30 * 3600) == "30 hours" and fw.span(3 * 86400) == "3 days" and fw.span(20) == "1 minute"
