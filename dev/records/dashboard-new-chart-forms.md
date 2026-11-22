# dashboard-new-chart-forms: Three chart forms: several series on one axis, an X/Y phase plot, a heatmap over time

depends-on: []

Problem: the owner asks for several flow rates on one graph, an X/Y plot of one measure against another and a heatmap. None exists: lineChart (ergostat/web/static/charts.js:192) draws one value line; cycleChart (charts.js:665) is the only point plot. /api/series already returns several refs on one time base (times, series[].values), so all three can be drawn on the client. The phase plot is listed under 'Later' in docs/proposals/charts.md; all three are recognised forms (decision 3).
Change: a new ergostat/web/static/plots.js (charts.js is 694 lines) using uPlot and the existing tokens and helpers (tok, baseOpts, mountPlot, rateUnit):
1. multiChart({times, series}): several series on one time axis, all rates in one unit (rateUnit over the largest), each line labelled at its end, line styles as well as colour telling them apart, cursor values for all.
2. phasePlot({x, y}): one series against another on the same buckets, joined in time order with direction ticks, the start an open point and the latest a filled one, axes labelled with name and unit, an optional desired level dashed on either axis.
3. heatmap({rows, times}): rows are refs (/api/series), a kind's states (/api/items-flow counts) or goals; columns are time buckets on one sequential token ramp with a scale key and the value under the cursor; an off stretch is hatched as well as coloured (filed Q76); each ref normalised to its own range is said in the key.
Each has an accessible name and a table fallback, reads in both themes, and is usable on its own until dashboard-xy-and-heatmap-panels registers it as a panel.
Definition of done:
1. multiChart for two flows of a served fixture shows two labelled lines in one unit.
2. phasePlot of one stock against another draws a joined path with its last point marked.
3. A heatmap of a kind's states has one row per state and as many columns as buckets.
4. Each renders in light and dark with no console errors, using tokens only (tests/test_style_tokens.py).
Files: new ergostat/web/static/plots.js, static/index.html (script tag), static/style.css, new tests/test_plots.py.
Acceptance tests: the three browser checks above on a test page that mounts each function with fixed data; a unit test of the bucket alignment.
Budget: 220 net lines of JS, 30 CSS, 60 tests.

Milestone: dashboard. Owner items: 18 (several flow rates on one graph, X/Y plot, heatmap). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. plots.js is 206 lines (multiChart, phasePlot, heatmap; alignPairs; heatOfSeries, heatOfStates and heatOfGoals to make
heatmap rows from /api/series, /api/items-flow and /api/loop-scope answers). style.css has 15 new lines, index.html one script tag,
and docs/proposals/charts.md has item 6 and a changed "Later" line. tests/test_plots.py has 114 lines: a unit test of the bucket
alignment (two refs on one time base, a reading in its own bucket), a check that plots.js holds no literal colour, and one browser
test run once in light and once in dark.
Overrun reason: tests/test_plots.py is 114 lines, not 60. The checks read the drawn canvas (each line's hue, the phase plot's first,
last and middle pixels, each heatmap cell's ramp step, the red hatch on an off stretch) so that each can fail. A DOM-only check could
not fail. That page script, the served fixture and the seed data take about 50 lines.
Choices nobody could confirm, each made the easier way to undo:
- The heatmap ramp reuses seven existing neutral tokens (--fill to --ink). No new tokens were added, so a ramp of its own is a
  token-block change for later.
- The test page is served by Playwright's route() in the test, not a file in the repository.
- phasePlot's done-item-2 check uses fixed data for two stand-in stocks ("queue", "done", in items). The served fixture
  (disk-space) has only one stock.
- A goal's heatmap row is |e| from its loop scope, on its own range, with its off stretches hatched.
Not covered by any test: the heatmap's value under the cursor, the phase plot's nearest-point hover, and heatOfSeries.
Screenshots were not taken (file tools and scratch scripts are confined to /work here), so how it looks was checked only by the
pixel samples in both themes. tests/test_plots.py is not one of the four browser files, so the merge queue runs it only if named.
Left for dashboard-xy-and-heatmap-panels: registering the three forms as panels.

Round 2, answering both findings of the round-1 review (no plots.js, CSS or HTML change):
- The browser checks for done items 1-4 now run in a gate. They moved into tests/test_diagram_rendering.py, one of the four
  browser files, as test_the_three_chart_forms_draw_in_each_theme. That file runs both themes against one served copy of
  disk-space and uses the file's own browser fixture and served(). dev/factory.toml was left unchanged.
  tests/test_plots.py keeps only the bucket-alignment unit test and the token check, so nothing in it is skipped for want
  of Playwright. The sentence above saying the merge queue runs it only if named no longer holds.
- The phase plot's "joined" check now samples (1.25, 1.75), a quarter of the way along (1,1)-(2,4) and away from the
  segment's direction tick. A new "apart" check also has to come out false at (1.75, 1.25), a point off the path.
- The multiChart check no longer counts pixels over the whole canvas. For each line it samples nine points along that
  line's first measured step in the left half, away from the end labels, and needs at least 5 of them, within a pixel,
  in the line's own hue (--g0, --g1).
- Each check was seen to fail: with the phase path's ctx.stroke() commented out, "joined" was false. With
  paths: () => null on multiChart's series (end labels still drawn), "lines" was [0, 0]. With the code restored, both
  themes pass ([9, 9]).
Overrun reason: the tests are 100 lines (74 in tests/test_diagram_rendering.py, 26 in tests/test_plots.py), not 60. The reason is the same as round 1's: the checks read the drawn canvas so that each one can fail, and the page script, the seed and the served fixture take about 50 of those lines.
