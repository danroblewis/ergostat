# module-box-sparklines: a closed module shows its headline measures as small line graphs

Owner, 2026-11-23: "I saw a neat feature briefly on the staging environment that gave the system dynamics modules line graphs ... it was cool", and "they were in the module boxes, probably sparklines."

Boxes once drew sparklines; on 2026-11-16 they moved into the module's panel (`moduleCharts` in `ergostat/web/static/charts.js`). Bring them back on closed modules only.

Change.
- In the Dynamics view, a closed module's box shows sparklines for at most three headline measures, chosen from the system's `show:`, else its goals' measures. Each has its name and current value, in the box's existing rows, with no new panel.
- Stocks, flows and auxiliaries stay as they are: no sparklines on them, so the stock-and-flow notation stays textbook.
- The line is a behavior over time on the page's time window, with a stated scale: it does not imply that two sparklines share a y axis. A missing or stale reading shows as a gap, never as a flat line or a zero.
- The diagram's structure draws first. Sparklines fill in afterwards from one batched request to the measurement store, refresh on the page's interval, and never move the layout or change a box's size.
- Clicking a module still opens its panel with the full charts.
- At a zoom where a sparkline would be unreadable it is not drawn.

Definition of done.
1. A closed module shows up to three sparklines with its current values; an open module, stock or flow shows none.
2. A browser test: positions of every box are identical before and after the sparklines load.
3. One batched request serves all visible modules, and it does not read the event log.
4. A series with a gap in its readings draws a gap.
5. tests/test_diagram_rendering.py passes on every example and view, in light and dark.

Files: ergostat/web/static/dynamics.js, ergostat/web/static/charts.js, tests.
