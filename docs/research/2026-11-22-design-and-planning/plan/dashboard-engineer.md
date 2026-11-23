# Owner item 18: a Dashboard page (engineer's notes, 2026-11-22)

Code read at DESIGN/ergostat main 2468c59b. Paths below are relative to that checkout.

## What the owner asked

A Dashboard page of configurable panels, each showing something that today lives on another page: a list of
items of a kind, a list matching a filter, counts of a kind over time, a stock (possibly measured outside), several
flow rates on one graph, an X/Y plot, projections, a nodes-and-edges diagram, a Gantt chart, a heatmap. "The
dashboard is an analysis." The owner's decision today overrides intent decision 1 (no new pages) for this page.

## Why it behaves as the owner says

The information is there, but each chart is wired to its own page, and some only appear inside a side panel:

- Items, counts over time (the cumulative flow chart): `pages.js:655-710`, built only per kind inside `pageItems`
  (`pages.js:551`, a 250-line function). It asks `/api/items-flow` every 30 s per open kind.
- Cycle-time scatter: `charts.js:665` `cycleChart`, only under a kind's table.
- A stock or flow over time, with replay, projection and fan: `charts.js:192` `lineChart`, `charts.js:275`
  `causesStrip`. Only in the Dynamics side panel (`charts.js:502` `sideCharts`). The only memory is "your charts",
  the last 3 parts in localStorage (`charts.js:493-500`).
- A goal's scope (r, y, u, e): `charts.js:530` `loopScope`, in the Blocks side panel and from Loops.
- Item lists for a set (kind, state, `where`, `moved`, `through`...): `itemsets.js:22` `itemsSection`, over
  `/api/items?...&alone=1` (`server.py:607-660`, `spec/item_sets.py:124` `parse`).
- Items Graph and Gantt: `relations.js:157` `relGraph(open)` and `relations.js:222` `relTimeline(open)`, each a
  self-contained component with `.draw(model, opts)`, fed by `/api/items-graph` (`server.py:705`).
- The model diagram: `diagram.js`, global state `S`, ELK layout. The only embedding today is the split pane, the
  whole page in an iframe with `?pane=1` (`split.js:1-40`).

What does not exist at all: a chart with several series on one axis (`lineChart` draws one value line plus its
own reference lines), an X/Y (phase) plot, a heatmap, and any saved or named arrangement of views. Nothing in
the docs mentions a dashboard except `docs/proposals/charts.md:17` ("never on a separate dashboard", now
overridden) and the "dashboarding subsystem" idea in `docs/proposals/parity/11-translating-both-ways.md:190`
(questions become displays), which is the right later tie-in for "the dashboard is an analysis".

## What it takes

The data side is nearly done; the page is mostly composition:

| Panel | Data (exists) | Drawing (exists?) |
|---|---|---|
| items of a kind / a filter | `/api/items` with the item-set params | `itemsSection` (needs a params entry point instead of a part's `info`) |
| counts of a kind over time | `/api/items-flow?kind=` | `flowChart` (charts.js:621) |
| cycle times | same | `cycleChart` |
| a stock (sensor from outside or not) | `/api/series?refs=stock.X` | `lineChart` / `causesStrip` |
| several flows on one graph | `/api/series?refs=flow.a,flow.b` (one call, one time base) | NEW: multi-series line chart |
| X/Y plot | `/api/series` with two refs on the same buckets | NEW: phase plot (uPlot points/path, time as order) |
| projections | `/api/series?...&replay=1&fan=1` | `lineChart` (projection, fan) |
| goal scope | `/api/loop-scope?goal=` | `loopScope` |
| nodes and edges | `/api/items-graph`; the model diagram via `?pane=1` | `relGraph`; iframe |
| Gantt | `/api/items-graph` | `relTimeline` (owner item 17 changes what it projects) |
| heatmap | `/api/series` (refs x buckets) or `/api/items-flow` (states x buckets) | NEW: heatmap, client-only |
| note (the analysis prose) | the dashboard's own text | `md()` (pages.js:245) |

Routing: `server.py:35` and `util.js:15` `UI_PAGES`, `util.js:508` the route table, `split.js:26`
`OTHER_PAGES`, `index.html:12` nav and the script list.

## Risks found

1. **Load.** Every `/api/*` head except `items-query` builds a snapshot (`server.py:451`), cached 1.5 s per
   `(window, at)` (`server.py:151-176`). A projection with fan took 3.5 s on software-factory (14 stocks); plain
   series 3 ms, items-flow 32 ms, items-graph timeline 0.42 s. The live factory (:8798) answered neither
   `/api/status` nor `/items` within 30 s while I timed it (owner item 2). Ten panels each polling, each with its
   own window, would multiply snapshots (each window is a new key) and fan runs. So: one window per dashboard
   (the header's), refs batched into one `/api/series` call, replay/fan panels lazy (only when on screen) and
   polled slower, and nothing polled while the tab is hidden (`util.js:402` `poll` already pauses).
2. **Decision 7 (people do not edit configuration through the page).** An arrangement of panels is a view, not
   the model; but a shared, named dashboard written from the page would be the first page write of
   configuration. The proposal must say where each kind of edit lands (below).
3. **pages.js is 1171 lines**; the dashboard must be its own file(s), not more in pages.js. `pageItems` holds
   the CFD and item list logic inline; panels need it as functions.
4. **The model diagram in a panel** costs a full ELK layout (owner item 10: far too slow). An iframe per diagram
   panel on a large model is a real risk; the proposal must cap it (one, lazy) or use a static drawing.
5. **R12** (fewer pages) and the Loops/Goals page: a Dashboard of goal scopes overlaps Loops. Not a blocker; the
   proposal should say whether a default dashboard could later replace a page.

## Storage: what the proposal must settle (my recommendation)

One panel schema, JSON-shaped, whose parameters are the very query parameters the existing APIs and pages
take (an item set's params as `itemsHref` writes them, `refs`, `goal`, `kind`, `view`), so a panel is "an
address on another page, drawn small", and every panel links to the full page view with the same params.

- **The reader's own arrangement:** in the address (`/dashboard?d=<compact JSON>`) and remembered per project
  in the browser (as split.js and "your charts" do). Editing it writes nothing on the server, so decision 7
  holds. Shareable as a link; exportable as YAML.
- **Shared, named dashboards:** a top-level `dashboards:` key in `ergostat.yaml`, compiled like `systems.*.show`
  (`spec/compile.py:908-913`, refs checked at `compile.py:1588`), written by the Supervisor or an agent ("make
  this the team's"), so its refs are checked by `ergostat check` and a renamed stock is a finding, not a blank
  panel. A display change touches no dynamics, so it should not need the full judge run (say how).
- **Later, the analysis:** a dashboard as an item (`ergostat.analysis`) authored by an agent from repeated
  questions (parity 11 §C), with the note panel as its argument. Not in the first build.

Also to settle: the panel types in v1; the grid (columns, sizes, phone width = one column); per-panel window
(recommend not in v1, for load); windows beyond 7 days (`main.js:6`) for an analysis; whether a dashboard goes
into a snapshot (`web/snapshot.py`) so an analysis can be attached to a document; nav position; how each panel
says its source and links to the full view; which chart forms are recognised (phase plot and heatmap are
standard; no invented panel types).

## Size

Large overall: needs a proposal first (storage, schema, load budget, decision-7 boundary). After it, three
incremental gaps: the page with the panels that reuse components; the three new chart forms; `dashboards:`
in the spec. A fourth, small, for snapshots, can wait.

## Overlaps

Q36 (the address holds the selection and window: the dashboard's state lives in the address the same way),
Q19 (the window never claims more than it holds: every panel inherits it), Q11 (loading shown: each panel shows
'Loading…' with its title), Q32 (a filter matching nothing says so: list panels), Q56 (CFD band labels: reused
component), Q59/Q60 (Timeline and finish estimates: reused component), Q76 (off as a mark: reused charts),
R12 (fewer pages), R6 (projection sentences), R1 (box rows: a goal row panel could reuse it). Owner items 2
(load), 15 (the kind page shares the item filter component), 17 (Gantt simulation feeds the Gantt panel),
1/13/14 (item list defaults and pagination: the list panel should use the same code, not a copy).
