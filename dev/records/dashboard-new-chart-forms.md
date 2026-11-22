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
