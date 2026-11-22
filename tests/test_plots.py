"""Acceptance (plots.js), the unit part: the bucket alignment the phase plot pairs by, and plots.js coloured only from
tokens. The browser checks (several flows on one axis in one unit, a phase plot's joined path and its marks, a heatmap
of a kind's states, in both themes with no console error) are in tests/test_diagram_rendering.py, one of the four
browser files the merge queue runs: test_the_three_chart_forms_draw_in_each_theme."""

import time
from pathlib import Path

from tests.test_series import get
from tests.test_style_tokens import COLOUR

ROOT = Path(__file__).resolve().parent.parent


def test_two_refs_share_one_time_base_and_a_reading_lands_in_its_own_bucket(project):
    now = time.time()
    project.events.add("ergostat.started", at=now - 600)
    project.measurements.add("sensor/disk-usage", 77, at=now - 600 + 250)          # bucket 2 of 6, 100 s each
    got = get(project, "series", refs="stock.disk-used,flow.cleaned", points=6)
    w = (got["until"] - got["since"]) / 6
    assert [round(t - got["since"] - (i + 0.5) * w, 2) for i, t in enumerate(got["times"])] == [0] * 6
    assert [len(s["values"]) for s in got["series"]] == [6, 6] and got["series"][0]["values"][2] == 77


def test_plots_js_is_coloured_only_from_tokens():
    assert not COLOUR.search((ROOT / "ergostat/web/static/plots.js").read_text())
