"""Acceptance (plots.js), the unit part: series on one time base, and plots.js coloured only from tokens. The browser
check (a heatmap of a kind's states and of a goal, in both themes with no console error) is in
tests/test_diagram_rendering.py, one of the four browser files the merge queue runs: test_the_heatmap_of_rows_draws_in_each_theme."""

import time
from pathlib import Path

from tests.test_series import get

ROOT = Path(__file__).resolve().parent.parent


def test_two_refs_share_one_time_base_and_a_reading_lands_in_its_own_bucket(project):
    now = time.time()
    project.events.add("ergostat.started", at=now - 600)
    project.measurements.add("sensor/disk-usage", 77, at=now - 600 + 250)          # bucket 2 of 6, 100 s each
    got = get(project, "series", refs="stock.disk-used,flow.cleaned", points=6)
    w = (got["until"] - got["since"]) / 6
    assert [round(t - got["since"] - (i + 0.5) * w, 2) for i, t in enumerate(got["times"])] == [0] * 6
    assert [len(s["values"]) for s in got["series"]] == [6, 6] and got["series"][0]["values"][2] == 77
