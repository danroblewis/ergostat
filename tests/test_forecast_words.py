"""A goal's forecast in words (numbers/forecast_words.py): the sentence forms, the odds as 'N in 10', the clock times,
and p, the runs and the horizon kept out of the sentence for its disclosure. Each chance is of whole runs (off, or back,
at some moment ahead), not of the worst single moment."""

from __future__ import annotations

import time

import pytest

from ergostat.numbers import forecast_words as fw

NOW = time.mktime((2026, 11, 22, 14, 0, 0, 0, 0, -1))      # 14:00 local


def got(runs, horizon=480.0, invalid=0):
    """closedloop.risk's answer for one goal from each run's off (1) or within (0) at each moment ahead; a run that is
    not valid is off at every moment, as risk counts it."""
    ends = [list(r) for r in runs] + [[1] * len(runs[0])] * invalid
    n, k = len(ends), len(ends[0])
    first_off = [next((i for i, v in enumerate(e) if v), k) for e in ends]
    first_on = [next((i for i, v in enumerate(e) if not v), k) for e in ends]
    p = [sum(e[i] for e in ends) / n for i in range(k)]
    return {"made": n, "invalid": invalid, "horizon": horizon, "stopped": None,
            "goals": {"users": {"p_off": p, "p_off_end": p[-1], "expected_off": 0.0,
                                "p_ever_off": [sum(f <= i for f in first_off) / n for i in range(k)],
                                "p_ever_on": [sum(f <= i for f in first_on) / n for i in range(k)]}}}


def crossing(at, k):
    """A run within until moment ``at`` (of ``k``) and off from then on; ``at`` None: within throughout."""
    return [0 if at is None or i < at else 1 for i in range(k)]


@pytest.mark.parametrize("q, said", [(0.0, "under 1 in 10"), (0.04, "under 1 in 10"), (0.05, "1 in 10"), (0.14, "1 in 10"),
                                     (0.15, "2 in 10"), (0.25, "3 in 10"), (0.65, "7 in 10"), (0.94, "9 in 10"),
                                     (0.95, "over 9 in 10"), (1.0, "over 9 in 10")])
def test_odds_are_said_as_n_in_10_rounded_half_up(q, said):
    assert fw.odds(q) == said
    assert fw.about(q) == (said if said[0] in "uo" else f"about {said}")


def test_a_goal_likely_to_hold_says_for_how_long_and_how_likely():
    w = fw.said(got([crossing(None, 4)] * 9 + [crossing(2, 4)]), "users", NOW)
    assert w["sentence"] == "Likely to stay within its bound for the next 8 minutes (about 9 in 10)"
    assert w["short"] == "within, 9 in 10"
    how = dict(w["how"])
    assert how["chance off at the horizon"] == "p≈0.1" and how["runs"] == "10" and how["horizon"] == "8 minutes, to 14:08"
    assert "p≈" not in w["sentence"] and "runs" not in w["sentence"] and "p≈0.1" in w["title"]
    sure = fw.said(got([crossing(None, 4)] * 20), "users", NOW)
    assert sure["sentence"] == "Likely to stay within its bound for the next 8 minutes (over 9 in 10)"   # no 'about'


def test_a_goal_likely_to_cross_says_around_when():
    runs = [crossing(0, 4)] + [crossing(1, 4)] * 2 + [crossing(2, 4)] * 2 + [crossing(3, 4)] * 2 + [crossing(None, 4)] * 3
    w = fw.said(got(runs, horizon=40 * 60), "users", NOW)
    assert w["sentence"] == "Likely to cross its bound around 14:30 (about 7 in 10)"
    assert w["short"] == "cross ~14:30, 7 in 10"


def test_runs_that_cross_at_different_moments_count_as_crossing():
    """Each run off at one moment only, a different one each: no moment has more than 1 in 10 off, but 8 in 10 runs
    cross; the worst moment's chance would say 'stay within (about 9 in 10)'."""
    runs = [[int(i == k) for i in range(10)] for k in range(8)] + [crossing(None, 10)] * 2
    w = fw.said(got(runs, horizon=100 * 60), "users", NOW)
    assert w["sentence"] == "Likely to cross its bound around 14:50 (about 8 in 10)"
    runs = [[int(i == k) for i in range(10)] for k in range(1, 5)] + [crossing(None, 10)] * 6
    assert fw.said(got(runs, horizon=100 * 60), "users", NOW)["sentence"] == \
        "Likely to stay within its bound for the next 2 hours (about 6 in 10)"


def test_a_goal_off_now_says_when_it_is_expected_back_or_that_it_stays_off():
    back = [[1] + [0] * 3] * 2 + [[1, 1, 0, 0]] * 3 + [[1] * 4] * 5
    assert fw.said(got(back, horizon=100 * 60), "users", NOW)["sentence"] == "Expected back within its bound by 15:15"
    # two runs come back for a moment and go off again: at the horizon every run is off, but 8 in 10 never came back
    w = fw.said(got([[1, 0, 1]] * 2 + [[1, 1, 1]] * 8, horizon=3 * 3600), "users", NOW)
    assert w["sentence"] == "Likely to stay outside its bound for the next 3 hours (about 8 in 10)"
    assert w["short"] == "off, 8 in 10"


def test_runs_not_valid_are_named_in_the_sentence_when_they_decide_it():
    w = fw.said(got([crossing(None, 3)] * 6, invalid=4), "users", NOW)
    assert w["sentence"] == ("Likely to stay within its bound for the next 8 minutes "
                             "(about 6 in 10; 4 of 10 runs not valid, counted as off)")
    assert dict(w["how"])["runs"] == "10 (4 not valid, counted as off)"
    w = fw.said(got([crossing(None, 3)] * 4, invalid=6), "users", NOW)
    assert w["sentence"] == ("Likely to stay outside its bound for the next 8 minutes "
                             "(about 6 in 10; 6 of 10 runs not valid, counted as off)")
    w = fw.said(got([crossing(None, 3)] * 99, invalid=1), "users", NOW)     # the same sentence without it: not named
    assert w["sentence"] == "Likely to stay within its bound for the next 8 minutes (over 9 in 10)"


def test_a_goal_with_no_forecast_says_why():
    w = fw.said(None, "users", NOW)
    assert w == {"sentence": "No estimate: too little history", "short": "no estimate", "title": "too little history", "how": []}
    nothing = got([crossing(None, 3)]) | {"made": 0}
    assert fw.said(nothing, "users", NOW, "no run could be made")["sentence"] == "No estimate: no run could be made"
    assert fw.said(got([crossing(None, 3)]), "other", NOW)["short"] == "no estimate"
    w = fw.said(got([[1, 1, 1]] * 4) | {"invalid": 4}, "users", NOW)      # every run made was not valid
    assert w["sentence"] == "No estimate: none of the 4 runs of the model was valid" and w["short"] == "no estimate"


def test_a_clock_time_on_another_day_names_the_day():
    assert fw.clock(NOW + 86400, NOW).endswith(" 14:00") and fw.clock(NOW + 86400, NOW) != "14:00"
    assert fw.span(30 * 3600) == "30 hours" and fw.span(3 * 86400) == "3 days" and fw.span(20) == "1 minute"
