"""The query engine's arithmetic (ergostat/query/buckets.py, transforms.py), each against values worked out by hand."""

from __future__ import annotations

import pytest

from ergostat.query import transforms as tf
from ergostat.query.buckets import aggregate, grid, percentile, step_of

VALUES = [4.0, 1.0, 3.0, 2.0]


@pytest.mark.parametrize("agg,want", [("count", 4.0), ("sum", 10.0), ("avg", 2.5), ("min", 1.0), ("max", 4.0), ("last", 2.0),
                                      ("p50", 2.5), ("p90", 3.7), ("p95", 3.85), ("p99", 3.97)])
def test_each_aggregation(agg, want):
    assert aggregate(agg, VALUES) == pytest.approx(want)


@pytest.mark.parametrize("agg", ["sum", "avg", "min", "max", "last", "p50", "p90", "p95", "p99"])
def test_an_empty_bucket_has_no_value(agg):
    assert aggregate(agg, []) is None


def test_an_empty_bucket_counts_zero():
    assert aggregate("count", []) == 0.0


def test_a_percentile_of_one_value_is_that_value():
    assert percentile([7.0], 99) == 7.0


def test_the_step_is_the_window_over_the_points_in_whole_minutes():
    assert step_of(86400, 120) == 720
    assert step_of(3600, 120) == 30
    assert step_of(100, 120) == 1
    assert step_of(86400, 120, 3600) == 3600
    assert step_of(86400, 120, 60) == 720          # never finer than the points allow


def test_the_grid_sits_on_multiples_of_its_step_and_cuts_its_ends_to_the_window():
    g = grid(1000.0, 1250.0, 5)                    # 50 s buckets, from 1000
    assert (g.step, g.start, g.n) == (50.0, 1000.0, 5)
    g = grid(1010.0, 1260.0, 5)                    # the same width, off the multiples: six buckets, its ends part ones
    assert (g.start, g.n) == (1000.0, 6)
    assert g.times[:2] == [1010.0, 1050.0]
    assert g.spans == [40.0, 50.0, 50.0, 50.0, 50.0, 10.0]
    assert sum(g.spans) == 250.0


def test_a_reading_at_the_windows_end_is_in_the_last_bucket():
    g = grid(1000.0, 1250.0, 5)
    assert (g.at(1000.0), g.at(1049.9), g.at(1050.0), g.at(1250.0)) == (0, 0, 1, 4)


def test_a_rate_is_per_second_of_what_each_bucket_covers():
    assert tf.plain_rate([10.0, None, 5.0], [10.0, 10.0, 2.5]) == [1.0, None, 2.0]


def test_a_counters_rate_with_a_reset():
    # readings 100 (before the window), 130, 160, then a restart to 20, then 50: increases 30, 30, 20 (from zero), 30
    assert tf.counter_rate([130.0, 160.0, 20.0, 50.0], [10.0] * 4, 100.0) == [3.0, 3.0, 2.0, 3.0]


def test_a_counters_rate_across_a_gap_is_spread_over_the_gap():
    assert tf.counter_rate([10.0, None, None, 40.0], [10.0] * 4, 0.0) == [1.0, None, None, 1.0]


def test_a_counter_with_nothing_before_the_window_has_no_first_rate():
    assert tf.counter_rate([5.0, 8.0], [1.0, 1.0], None) == [None, 3.0]


def test_delta_skips_a_gap():
    assert tf.delta([1.0, 4.0, None, 2.0]) == [None, 3.0, None, -2.0]


def test_cumulative_holds_through_a_gap_and_starts_at_the_first_value():
    assert tf.cumulative([None, 1.0, None, 2.0]) == [None, 1.0, 1.0, 3.0]


def test_a_moving_average_reads_what_its_window_holds():
    assert tf.moving_avg([2.0, 4.0, None, 6.0, None, None, None], 2) == [2.0, 3.0, 4.0, 6.0, 6.0, None, None]


@pytest.mark.parametrize("per_second,want", [(2.0, "second"), (0.5, "minute"), (0.001, "hour"), (0.00002, "day"), (0.0, "day")])
def test_a_rates_unit_of_time_is_the_shortest_that_reads_at_least_one(per_second, want):
    assert tf.per_for([None, per_second]) == want
