# Owner item 18: the Dashboard ("the dashboard is an analysis")

Designer notes, 2026-11-22. Read only; screenshots in `shots/plan-dash-*.png`.

## What a user sees today

The pieces the owner wants on one page all exist, each on a different page and each found differently:

| Owner's panel | Where it is today | Renderer / API (reusable) |
|---|---|---|
| items of a kind; items matching a filter | Items page List, long scroll (`plan-dash-sf-items.png`); a stock's or flow's side panel ("Items in it") | `pages.js` items table, `itemsets.js itemsSection`; `GET /api/items?kind&state&where&moved` (`spec/item_sets.py`, the same set the address carries) |
| counts of a kind over time | Items page, the per-kind state chart (CFD) above each table (`plan-dash-tf-timeline.png`) | `GET /api/items-flow?kind=K` |
| a stock (also an external one) | Diagram: click the stock, its side panel (`plan-dash-sf-users-panel.png`) | `charts.js lineChart`, `GET /api/series?refs=stock.X` |
| several flow rates on one graph | nowhere on one axis: the causes strip stacks them, one chart each | `/api/series` already takes several refs; a multi-line chart is new |
| X/Y plot | only the cycle-time scatter (items) | new chart form (SD's phase plot; charts.md lists it under "Later") |
| projections | the stock panel: replay dashed, projection lighter, fan shaded | `/api/series?...&replay=1&fan=1` |
| nodes-and-edges diagram | Diagram page (pan and zoom), Items Graph | `diagram.js` / `dynamics.js` / `blocks.js`, `/api/graph`, `/api/items-graph` |
| Gantt | Items Timeline (`plan-dash-tf-timeline.png`) | `/api/items-graph`, `eta_api.py` |
| heatmap | nowhere | new chart form |
| (implied) the goals and whether they hold | Loops page table (`plan-dash-sf-loops.png`); module panel's "Its measures, on one time axis" (`plan-dash-sf-product-module.png`) | `/api/loops`, `charts.js moduleCharts` |

So the problem the owner names is real and is a composition problem, not a missing-data problem: nine of the
eleven panel kinds are drawn already; two chart forms (X/Y, heatmap) are new. The design work is (1) where a
dashboard is stored and who changes it, (2) one cheap way to fetch many panels, (3) how a reader configures it
without breaking "read-only for people".

Timing: the demos answer fast (`:8796 /api/status` 0.04 s, `/api/series` with three refs and replay 0.15 s,
`/api/items?kind=..&n=10` 0.002 s). The live factory (:8798) answered nothing within 60 s (`/api/status`,
`/api/items`, `/api/items?kind=gap`) and not even `/static/style.css` within 20 s while I probed: the server was
saturated (owner item 2). A dashboard that fires one request per panel every five seconds would make that worse.
Its fetch must be one request per poll, computed on the one shared snapshot (`Live.snapshot`, already shared by
the requests of one moment), with per-panel time limits and a slow poll.

## The design

**A dashboard is part of the model, like `show:`.** The model already declares displays: a system's `show:` says
what its closed box shows (SPEC §4a), and the parity proposal's "display loop" (docs/proposals/parity/
11-translating-both-ways.md §C) has display changes travel as `ergostat.model-change` items the judge passes at
once. This is also the SD tools' practice: Vensim's custom graphs (several variables on one graph, X-Y graphs) and
Stella's interface pages are stored with the model, named, and versioned with it. So: a top-level `dashboards:`
key, in any model file; one in a system's file is namespaced by that system (decision 5). Kept in the YAML, it is
versioned, shared by everyone who reads the project, held in snapshots, and can be proposed by agents.

```yaml
dashboards:
  factory-week:
    description: is the factory keeping up, and when does the backlog clear
    window: 7d                       # optional: else the page's window
    panels:
      - note: "The question: does review capacity, not workers, limit delivery?"
      - goals: [requests-handled, all-live]
      - chart: [stock.backlog]  ; projection: true          # replay, projection, fan
      - chart: [flow.started, flow.finished, flow.reviewed]  # one axis, one time base
      - xy: [stock.backlog, flow.finished]                   # a phase plot
      - items: {kind: gap, state: [queued, active]}          # the Items page's set, same keys
      - states: gap                                          # counts of a kind over time (CFD)
      - timeline: {kinds: [gap]}                             # Gantt, with completion estimates
      - heatmap: {rows: goals, value: error}
      - diagram: {view: dynamics, system: factory}
```

(Exact syntax is the proposal gap's job; the shape is one key per panel naming its kind, its subject in the model's
own references, and a few options.) `check` validates every reference (`bad-dashboard-ref`), so a renamed stock is
a finding, not a blank panel.

**"The dashboard is an analysis."** Each panel shows the model's reading beside the measurement, never a bare
number: a stock with its replay, projection and when it crosses its goal's bound; flows on one time base with their
balance (in − out) against the stock's change; an X/Y with the model's own path drawn over the measured one; a
Gantt from the completion estimates; a list with its count and how that count is moving. Panels may carry a
`note:` (markdown), so a dashboard reads as a short study: question, evidence, what the model says. It follows the
page's window and time travel, exports (R10) and is held in a snapshot, so it can go into a design doc.

**Configuring it, inside the owner's rules.** People do not edit configuration through the page; the owner's
what-if already shows the allowed path (owner-made proposal, then Accept writes the YAML). The same here:
- Every chart, item list and timeline elsewhere gets "Add to dashboard"; a panel's menu edits its subject, window
  and kind, reorders or removes it. Until kept, the dashboard is a **draft**, held in the address (shareable) and in
  the browser (like "your charts" in `charts.js`), written nowhere.
- "Keep" makes an `ergostat.model-change` of kind `display`, made by `owner`, with the YAML diff. It changes no
  dynamics, so the judge passes it at once; Accept writes it, exactly as a what-if is accepted.
- The Supervisor and agents propose dashboards the same way (the display loop), and the owner accepts.

**Where it sits among pages.** The owner overrode "no new pages" for this one. To keep R12's direction (fewer
pages) the Dashboard should be where the Goals table ends up: the Goals table is one panel kind (`goals`), and with
no dashboard declared the page shows one made from the model (each top system's `show:` measures and its goals,
the same data R1 puts on the closed box). Whether Goals then folds into Dashboard is the owner's call (question
below); R12 already says "revisit Loops after R1".

## Agreement and conflict with the review

- Conflict: intent decision 1 and the whole review forbid new pages and panels; the owner's explicit request
  overrides it for this page. The review's spirit is kept by building every panel from an existing renderer, adding
  only two recognised chart forms (phase plot, heatmap), and letting the Dashboard absorb the Goals table.
- Agree: decision 3 (recognised diagrams only): X/Y is the SD phase plot, Gantt and CFD are workflow practice,
  heatmap is a standard chart; nothing invented. The diagram panel is the Diagram itself, not a new diagram.
- Agree: decision 7: drafts write nothing; keeping is an owner-accepted proposal like the what-if.
- Combine with R1: the default dashboard and the `goals` panel use the same per-goal row (value, bound, trend,
  status word) R1 draws on the closed box; build that row once.
- Combine with R10 (export) and the snapshot: a dashboard is the natural unit to export into a document.
- Combine with owner item 17: the `timeline` panel shows whatever the simulated timeline produces; it does not wait
  for it, but improves with it.
- Combine with owner item 2: the batched endpoint is a requirement, not an optimisation.

Filed quick fixes this builds on (not re-proposed): Q19 (window never claims more than the record: panels inherit
it), Q20/Q21 (one rate per flow, one time base per system: required for "several flows on one graph"), Q23 (a goal's
bound written one way: the goals panel uses it), Q36 (the address holds selection and window: drafts use the same
address pattern), Q56 (every band of the state chart labelled: the `states` panel reuses it), Q59/Q60 (timeline
without relations; finish estimate as clock time: the `timeline` panel reuses them), Q76 (off as a mark: the
heatmap's off cells and the scope charts), Q72 (goals as cards on a phone: the goals panel at narrow width).

## Gaps

1. `dashboard-proposal` (incremental): the design doc; settles syntax, panel kinds, the batched API, editing path.
2. `dashboard-declaration-and-api` (incremental): `dashboards:` in the model, schema, `check`, `GET /api/dashboard`.
3. `dashboard-page-existing-panels` (incremental): the page, with the panels whose renderers exist.
4. `dashboard-xy-and-heatmap-panels` (incremental): the two new chart forms.
5. `dashboard-diagram-panel` (incremental): a Diagram or Items Graph address drawn read-only in a panel.
6. `dashboard-add-and-keep` (incremental): Add to dashboard, drafts, Keep as an owner display proposal.

Order: 1, then 2 and 3 in parallel (3 against a fixture answer), then 4, 5 and 6 in parallel.

## Questions for the owner (one sentence each)

- Should the Goals page become the default dashboard (its table one panel), so the page count does not grow?
- Is one dashboard per project enough to start, or do you want several named ones from day one?
- May a dashboard you keep be written into the model file through Accept, as a what-if is?
