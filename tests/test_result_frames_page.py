"""Acceptance (result-frames-and-verdicts), the page's half, in a real browser with the real chart families and answers
made by the real server code (tests/test_result_frames_and_verdicts.py is the server's half):

- a refused answer is drawn by no family: the panel says it is refused, why, and the fix (done 2, 3);
- a warned answer is drawn, with its warning and fix on the chart (done 3);
- the latency heatmap (chart 16) draws the hand-worked histogram: a column a time, a row a bucket labelled by its
  bounds, the time with no count left a gap (done 1);
- the phase portrait (chart 14) draws two signals, and draws nothing of a refused answer;
- what is not measured says so, and a graph's edges are a table's rows.

    uv run --with playwright==1.63.0 python -m pytest tests/test_result_frames_page.py
"""

from __future__ import annotations

import pytest

from tests import test_plot_forms as forms
from tests import test_result_frames_and_verdicts as server
from tests.test_plot_forms import PAINTED, Site, config, playwright
from tests.test_result_shapes import samples
from tests.test_result_shapes_page import FAMILIES, STATE

browser, histogram = forms.browser, server.histogram     # (fixtures)
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

T = server.T
META = {"now": T + 480, "since": T, "until": T + 480, "step": 120}
PANEL = "(id) => document.querySelector(`[data-panel-id=\"${id}\"]`)"
TEXT = f"([id, sel]) => ({PANEL})(id).querySelector(sel)?.textContent ?? null"


def words(s, pid, sel):
    return s.page.evaluate(TEXT, [pid, sel])


def test_a_refused_answer_is_drawn_by_no_family_and_says_why_and_the_fix(browser, tmp_path, histogram):
    bad, two = server.asked(tmp_path, histogram, "bad", "two")
    s = Site(browser)
    try:
        for got in (bad, two):
            [reason] = got["meta"]["verdict"]["reasons"]
            for family in FAMILIES:
                pid = f"{reason['code']}-{family}"
                s.mount(config(family, pid=pid), {**got, "id": "a"}, META)
                s.page.wait_for_timeout(30)
                assert s.page.evaluate(STATE, pid) == "error", (family, reason["code"])
                assert s.page.evaluate(f"(id) => ({PANEL})(id).querySelectorAll('canvas').length", pid) == 0, family
                assert words(s, pid, ".panel-message-head") == "Refused", family
                assert words(s, pid, ".panel-message-text") == got["error"], family
                assert words(s, pid, ".panel-message-fix") == f"Fix: {reason['fix'][0].upper()}{reason['fix'][1:]}.", family
                s.clear()
        assert not s.errors, s.errors
    finally:
        s.close()


def test_the_latency_heatmap_draws_the_hand_worked_histogram_with_its_warning(browser, tmp_path, histogram):  # chart 16
    [got] = server.asked(tmp_path, histogram, "sum by (le) (increase(wait_seconds_bucket[2m]))")
    s = Site(browser)
    try:
        s.mount(config("heatmap", pid="lat"), {**got, "id": "a"}, META)
        assert s.page.evaluate(STATE, "lat") == "drawn" and s.page.evaluate(PAINTED, "lat") > 2
        m = s.model()
        assert m["counts"] == [[2, 3, 1], [0, 4, 5], [], [1, 0, 0]]          # a column a time; the third is a gap
        assert m["xEdges"] == server.TIMES + [T + 480] and m["yEdges"] == [0, 1, 2, 3]
        assert m["top"] == 5 and m["total"] == 16                            # (3 more above le=1, said, not drawn)
        warned = s.page.locator('[data-panel-id="lat"] .panel-warning').inner_text()
        assert "3 of 19 are above the highest bound (le=1), and are not drawn. Add a bucket above the highest bound" in warned
        for family in ("bar", "histogram"):                                  # the window's counts, a bar a bucket
            s.mount(config(family, pid=family), {**got, "id": "a"}, META)
            assert s.page.evaluate(STATE, family) == "drawn" and s.page.evaluate(PAINTED, family) > 2, family
        assert not s.errors, s.errors
    finally:
        s.close()


def test_the_bucket_rows_are_labelled_by_their_bounds(browser, tmp_path, histogram):
    [got] = server.asked(tmp_path, histogram, "sum by (le) (increase(wait_seconds_bucket[2m]))")
    s = Site(browser)
    try:
        s.mount(config("heatmap", pid="lat"), {**got, "id": "a"}, META)
        said = s.page.evaluate("""() => { const c = last.querySelector('.plot-cursor'), r = c.getBoundingClientRect(), out = [];
          for (const f of [0.2, 0.5, 0.8]) {
            const at = { clientX: r.left + r.width * 0.3, clientY: r.top + r.height * f, bubbles: true };
            c.dispatchEvent(new PointerEvent('pointermove', at));
            out.push(last.querySelector('.panel-readout')?.textContent || '');
          }
          return out; }""")
        assert [x.split("; ")[1].split(":")[0] for x in said] == ["0.5 to 1", "0.1 to 0.5", "0 to 0.1"], said
        assert not s.errors, s.errors
    finally:
        s.close()


def test_the_phase_portrait_draws_two_signals_and_nothing_refused(browser, tmp_path, histogram):          # chart 14
    got = samples(tmp_path / "s")
    [bad] = server.asked(tmp_path, histogram, "bad")
    s = Site(browser)
    try:
        for name in ("two-signals", "points-in-time"):
            s.mount(config("phase", pid=name), got[name], META)
            assert s.page.evaluate(STATE, name) == "drawn" and s.page.evaluate(PAINTED, name) > 2, name
        s.mount(config("phase", pid="bad"), {**bad, "id": "a"}, META)
        assert s.page.evaluate(STATE, "bad") == "error" and words(s, "bad", ".panel-message-head") == "Refused"
        assert not s.errors, s.errors
    finally:
        s.close()


def test_what_is_not_measured_says_so_and_a_graphs_edges_are_a_tables_rows(browser, tmp_path):
    got = samples(tmp_path)
    s = Site(browser)
    try:
        s.mount(config("bode", pid="model"), got["model"], META)
        assert "From the model, not measured." in s.page.locator('[data-panel-id="model"] .panel-warning').inner_text()
        s.mount(config("bode", pid="data"), got["frequency"], META)
        said = s.page.evaluate(TEXT, ["data", ".panel-warning"]) or ""
        assert "not measured" not in said, said                                         # derived from measurements
        s.mount(config("table", pid="g"), got["graph"], META)
        rows = s.page.locator('[data-panel-id="g"] tbody tr .panel-series-name').all_inner_texts()
        assert sorted(rows) == ["a → b (blocks, declared) · wait", "b → c (blocks, declared) · wait"]
        assert not s.errors, s.errors
    finally:
        s.close()
