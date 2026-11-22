# Charts: behaviour over time, beside the model

Status: planned 2026-11-16, built 2026-11-16. As built: a flow's rate counted from the record (items
moving, or its valve's openings, which come after items and before the stock's changes) is counted
over a twelfth of the window, so one event is not a spike; a kind's items finish in the states after
its first that no item has left (else its last state); the Goals page's old trend in a goal's panel
is replaced by its scope.

## What the owner asked for

"We definitely need charts of stocks over time and of flow rates over time." Control charts maybe.
Asked where a system dynamics engineer and a control engineer would put them. The standing rules:
no new pages or panels; each diagram true to its discipline.

## The answer: charts live next to the model, chosen from it

Both disciplines read behaviour beside the structure, never on a separate dashboard:

- **System dynamics:** behaviour-over-time graphs, and Vensim's *Causes Strip*: select a
  variable and see it, and what drives it, stacked on one time axis.
- **Control:** a scope per loop: setpoint and measurement together, the control output below,
  the error below that, on one time axis.
- **Items (workflow practice):** the cumulative flow diagram (items in each state, stacked over
  time; bands are stocks, slopes are flows) and cycle-time scatter.

## What is built

1. **Causes strip, Dynamics view, in the side panel.** Clicking a stock shows the stock over the
   window, then each inflow and outflow as observed rates (per hour), stacked, one shared time
   axis, with the stock's desired level drawn where a goal holds it. Clicking a flow shows its
   rate, then what drives it (its `driven-by` and the stocks around it). An auxiliary: its
   value, then what drives it. Several parts selected (Shift-click or the selection box): each
   one's strip, same time axis. The parts the user charted last are remembered (per project, in
   the browser) and shown when nothing is selected: "your charts".
2. **Scope, Blocks view, in the side panel.** Clicking a loop's comparator, controller or its
   process output shows r and y on one plot (y measured, r dashed, the tolerance band shaded),
   u below (the control output: the actuator's moved amount or the knob's value, marking
   saturation at its limits), e below, one time axis; with the loop's numbers (time off, back
   in, saturated share, last decision). The Goals page's sparklines open the same scope.
3. **Items page.** Each kind: a cumulative flow diagram (its states stacked over the window, in
   state order) in place of the one-line counts; under each kind's table, a cycle-time scatter
   (each finished item: when it finished × how long it took), with the median line.
4. **Hover anywhere on a chart:** a vertical cursor shared across the strip, values at that
   moment; the same moment highlighted on every chart in the panel (synchronised cursors).
5. **The time window is the page's** (the "Last 1h" control): every chart follows it.

## How

- **Data:** one API, `GET /api/series?refs=stock.x,flow.y,auxiliary.z&window=…&points=N`,
  returning each ref's points (time, value) from the measurements store, bucketed to N points
  (mean per bucket; a stock's last value per bucket), its unit, its kind, and for a goal's stock
  its setpoint and tolerance. Flow rates are the flow's own sensor readings (per hour) where it has
  one, else derived from item moves, else from the stock's successive readings (`changes`).
  `GET /api/loop-scope?goal=g` returns r, y, u, e for the loop. `GET /api/items-flow?kind=k`
  returns per-state counts over time and finished items' cycle times, from the record.
- **Drawing:** uPlot (MIT, about 45 KB), vendored in `web/static/` like the other libraries,
  for time series (fast, synchronised cursors). The cumulative flow diagram and the scatter as
  uPlot too (stacked bands, points). Styled only with the design tokens: one ink and greys; the
  desired level and r dashed; red only for time a loop was off; no legends where a label at
  the line's end will do.
- **Snapshots:** the series a snapshot's charts need are included, so charts work offline.
- **Tests:** API unit tests (bucketing, rates by each source, scope fields, items flow); browser
  tests that clicking a stock, a flow, a loop, and an item kind draws its charts without errors,
  with the shared cursor; the style-token test still passes.

## Later

Comparative runs on the causes strip beyond one what-if (the replay, the projection, its sensitivity fan and a
what-if are built: SPEC §12b); phase plots; SPC charts on measured auxiliaries. (Step responses and Bode
plots in the block panels are built, from identified processes: SPEC §12d.)
