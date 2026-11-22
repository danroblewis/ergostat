# Dashboard: an analysis page of panels, where it is kept, and what it may cost

Status: proposed 2026-11-22 (gap dashboard-proposal). Nothing here is built. It settles the design questions the
follow-on gaps (section 9) cannot settle alone, and asks the owner one question (below).

## What the owner asked for

A Dashboard page of configurable panels: "the dashboard is an analysis". This request overrides the standing rule
"no new pages or panels" for this one page (recorded in `docs/DECISIONS.md`). Every other rule holds: each chart is
one its discipline would recognise (`docs/proposals/charts.md`), the diagram stays primary (invariant 9), and
people do not edit configuration through the page (the design review's decision 7). Writing the model is the
Supervisor's or ergostat's on the owner's answer, never a person's.

**The owner's one question.** *Is a dashboard kept in the address and the browser, declared in the model, or both,
with one window for all its panels?* The recommendation is **both, with one window**: a reader's draft lives in the
address and in localStorage and writes nothing; a shared dashboard is declared under `dashboards:` and reaches the
model only through a proposal the owner accepts. Each part can be built and removed alone, so it is the most
reversible choice. Until the owner answers, only the first part is built (dashboard-page-v1), and it writes nothing.

## What already exists

Nine of the eleven chart panel kinds are drawn today, each built into one page:

| What | Where it is drawn | Its data |
|---|---|---|
| item lists | `itemsSection` (`web/static/itemsets.js:22`) | `GET /api/items` (`web/server.py:607-657`) |
| states over time (cumulative flow) | `flowChart` (`charts.js:621`), in `pageItems` (`pages.js:552`, drawn at `:709`) | `GET /api/items-flow?kind=` (`server.py:709`, `series.items_flow`) |
| cycle time | `cycleChart` (`charts.js:665`), in `pageItems` (`pages.js:757`) | the same `items-flow` answer's `finished` |
| a stock, flow or auxiliary over time, with replay, projection and fan | `lineChart` (`charts.js:192`) inside `causesStrip` (`charts.js:275`) | `GET /api/series?refs=&replay=1&fan=1` (`server.py:659`, `numbers_api.add_to_series`, `numbers_api.py:217`) |
| goal scope (r, y, u, e) | `loopScope` (`charts.js:530`) | `GET /api/loop-scope?goal=` (`server.py:685`) |
| items graph | `relGraph` (`relations.js:157`) | `GET /api/items-graph?kinds=&system=` (`server.py:705`, `relations_api.graph`) |
| timeline (Gantt) | `relTimeline` (`relations.js:222`) | the same `items-graph` answer |
| the diagram | `drawGraph` (`diagram.js:644`), reading the global state `S` | `GET /api/graph` |

The diagram cannot be drawn twice on one page today: it reads and writes the global `S`. Its one second copy is the
split pane, which is the whole page in a frame (`?pane=1`, `split.js:1-40`). Nothing stores an arrangement of
charts. The nearest thing is "your charts": the parts a reader charted last, kept in localStorage under
`ergostat.charts.<project>` (`charts.js:493-500`). Every `/api` answer starts with one snapshot of the state per
(window, moment, model version). It is made once however many ask, kept 1.5 s when live and until the model changes
for a past moment (`Live.snapshot`, `server.py:151-176`).

## 1. The panel format

A dashboard is a title, one window, and a list of panels. A panel is a JSON-shaped mapping, written the same way in
the address (JSON) and in the model (YAML):

| Key | Meaning |
|---|---|
| `panel` | its kind, one of section 2's (named `panel` so that `kind` stays the item kind, as the APIs name it) |
| `title` | optional; by default the kind's own words ("ticket: states over time") |
| `size` | `s`, `m`, `l` or `full`: a third, half, two thirds or all of the row at desktop width; `tall` doubles the height |
| `note` | optional: one sentence under the title, saying why the panel is here |
| the kind's parameters | **exactly those its endpoint and page address already take**, by the same names |

Nothing new is invented for the parameters. A `chart` panel takes `/api/series`'s `refs`, `points`, `replay`, `fan`,
`inputs`, `loops` and `whatif`. An `items` panel takes `/api/items`'s `kind`, `state`, `where`, `moved`,
`moved_since`, `moved_until`, `through`, `followed`, `search` and `n` (`spec/item_sets.py:116-128`). A `scope`
panel takes `goal`. An `items-graph` or `timeline` panel takes `kinds` and `system` (`relations_api.py:19-23`). A
`diagram` panel takes the Diagram address's `view`, `system` and `open`. The window and the moment (`since`, `at`)
are the dashboard's, never a panel's (section 6). Every panel's title links to its full view with the same
parameters: an `items` panel to `/items?kind=ticket&state=review`, a `chart` to the Diagram with its refs chosen and
the causes strip open, a `scope` to the Blocks view with its loop chosen, a `diagram` to `/diagram?view=…&system=…`.
A panel is a window onto a page that already exists, never a second version of it.

## 2. The v1 panel kinds

Each kind maps to its endpoint and to the function it reuses, or is marked **new**. Each is a chart form its
discipline recognises:

| Kind | Endpoint | Reuses | The form, and whose it is |
|---|---|---|---|
| `note` | none (its one parameter is `text`) | the page's Markdown, `marked.parse` as at `pages.js:256` | a caption; text only, never a measure |
| `goals` | the state's goals | `goalRow` (`goalrow.js`): the shared goal row (section 4) | the control room's overview line (ISA-101 level 1) |
| `items` | `/api/items` | `itemsSection` (`itemsets.js:22`) | a work-item list, as on the Items page |
| `states` | `/api/items-flow` | `flowChart` (`charts.js:621`) | the cumulative flow diagram (Kanban practice; Reinertsen, *The Principles of Product Development Flow*, 2009) |
| `cycle-time` | `/api/items-flow` | `cycleChart` (`charts.js:665`) | the cycle-time scatter with its percentile lines (Vacanti, *Actionable Agile Metrics*, 2015) |
| `chart` | `/api/series` | `lineChart` (`charts.js:192`), one or several refs stacked on one axis as `causesStrip` (`charts.js:275`) stacks them | the behaviour-over-time graph (Sterman, *Business Dynamics*, 2000, ch. 2) |
| `xy` | `/api/series` (two refs) | **new**, on `baseOpts` (`charts.js:35`) and uPlot's scatter mode | the phase plot, one variable against another over time (Sterman ch. 4; Strogatz, *Nonlinear Dynamics and Chaos*) |
| `heatmap` | `/api/items-flow` (finished items) | **new**, on `baseOpts` | the latency heat map: time × duration band, shade by count (Gregg, "Visualizing System Latency", ACM Queue, 2010) |
| `scope` | `/api/loop-scope` | `loopScope` (`charts.js:530`) | the loop scope: setpoint and measurement, control output, error (Åström and Murray, *Feedback Systems*) |
| `items-graph` | `/api/items-graph` | `relGraph` (`relations.js:157`) | the precedence network (PERT; process mining's dependency graph, van der Aalst) |
| `timeline` | `/api/items-graph` | `relTimeline` (`relations.js:222`) | the Gantt chart |
| `diagram` | `/api/graph` | `drawGraph` (`diagram.js:644`), once it draws into a state of its own (section 9) | the stock-and-flow, block or process diagram, folded as the panel's `open` says |

Kinds left out of v1: SPC charts, Bode and step responses, dominance charts. They belong to the panels they are in
today, and charts.md lists them as later. A form with no citation is not a kind.

## 3. The analysis rule

"The dashboard is an analysis" means every panel shows **the model's reading beside the measure**. A count with
nothing beside it is a status board. The panel draws the reading in the same frame as the measure and says it in
words below, with the "low confidence" wording of `fanSaid` and `noReplaySaid` (`charts.js:438-463`) when the model
fits badly (honest numbers over flattering ones):

| Kind | The measure | The model's reading beside it |
|---|---|---|
| `goals` | each goal's value against its hold | the server's `word`, and where the projection crosses the hold within the window ahead (the bound crossing) |
| `items` | the items and their states | each open item's completion estimate, p50 and p90 (the `eta` `/api/items` already adds, `server.py:654-657`) |
| `states` | items in each state over time | balance: arrivals against departures over the window, and Little's law (WIP = throughput × cycle time) against the counted WIP |
| `cycle-time` | each finished item's time | the open items' estimates drawn as their own marks past now |
| `chart` | the readings | replay (dashed) over the window; projection, and fan when asked, past now (`add_to_series`) |
| `xy` | the measured trajectory | the replay's trajectory beside it |
| `heatmap` | finished items' times, shaded | the estimate's p50 and p90 drawn across as lines |
| `scope` | r and y, u, e | the loop's numbers (time off, saturated share, last decision), as `loopScope` prints them |
| `items-graph`, `timeline` | the relations and spans | the critical path and the estimates (`eta_api.merge`, `server.py:705-708`) |
| `diagram` | the closed boxes' readings | each box's health and trend, as the diagram already draws them |

A `note` has no measure, so it needs no reading. A `chart` panel over a part with no equation, so no replay, says
so in words (`noReplaySaid`). It never leaves the space empty without saying why.

## 4. The home page, and goals

`/` stays the folded diagram. The design review's decision 1 is that the diagram with everything folded away is
the control panel (SPEC §4a: "With every system closed, the diagram is the model's control panel"). The Dashboard
is an analysis page that a reader goes to in order to study something, and it is never the first answer to "is it
healthy". The brand link and `/` keep going to `/diagram` (`index.html:11`).

The `goals` panel is the shared goal row, `goalRow` in `goalrow.js`. Its counts (how many goals are off) come from
`state.goals_off`. Every panel that prints a goal's state prints the server's `word` for it, and never works out
"off", "near" or "on" from the numbers in the browser. That way the dashboard can never disagree with the diagram's
boxes or the goal row elsewhere. **None of `goalrow.js`, `state.goals_off` or `word` is on main as this is
written.** dashboard-page-v1 therefore depends on the gap that lands them and waits for it. It does not draw goals
another way in the meantime.

## 5. Storage

This is the question the owner answers. The proposal has three parts, each with its reasons.

**A reader's draft: in the address and in localStorage, nothing written.** A draft is the dashboard as JSON,
base64url-encoded in the address: `/dashboard?draft=…&since=1d`. The panel cap (section 6) keeps that under about
4 KB. The address always wins, so a link opens exactly what was sent. The last draft per project is also kept in
localStorage under `ergostat.dashboard.<project>`, built the same way as `chartsKey` (`charts.js:493`). Opening
`/dashboard` with no address reopens it there. Nothing reaches the server. A person shares a draft with **Copy
link**. The page never shows YAML for a person to paste: that would be people editing configuration, which decision
7 rules out.

**Shared, named dashboards: a top-level `dashboards:` key, compiled and checked like `systems.*.show`.**

```yaml
dashboards:
  NAME:
    title: TEXT               # optional
    window: 1d                # optional: the window it opens with (section 8)
    panels: [PANEL, ...]      # section 1's mappings
```

The compiler reads it as it reads `systems:` (`spec/compile.py:907-913`). Unknown keys are errors (`self.keys`).
Every ref is checked with `self.refs` and reported as `unknown-ref` when it names nothing, as `show:` refs are at
`spec/compile.py:1585-1588`. Each `panel` kind, `goal` and item `kind` must exist. The caps are checked at compile time and
refused as `bad-dashboard`. `dashboards:` describes no dynamics, so it stays out of the structure fingerprint and
out of the replay's inputs, and adding a dashboard is not a structural change. `/dashboard/NAME` opens it, and the
reader's changes to it become a draft in the address.

**How a draft is kept.** A draft becomes a declared dashboard only through an `ergostat.model-change` of a new kind,
**`display`**. Today's kinds are parameter, equation and structure. The page's **Keep** button files the proposal,
and it carries the draft's JSON. It is accepted the way a what-if's proposal is: by the owner's Accept, through
`numbers_api.post`'s `proposals/ID/accept` (`numbers_api.py:737-786`), the page's only kind of write and always the
owner's own act. The YAML edit is ergostat's, made from the JSON. The Supervisor may file the same proposal itself
(parity 2.11 §C: a question asked again and again becomes a display proposal). The person keeping a draft never
writes or sees configuration, and the model is written on the owner's answer, as with every accepted proposal.

**Does a display-only change skip the judge's replay?** Yes. It changes nothing the replay reads, so the replay
before and after would be the same and running it proves nothing (parity 2.11 §C: "a display change alters no
dynamics and no replay"). It is still compiled and checked before it is offered. By default it still waits for the
owner's Accept, because display is not one of the classes the owner has named `auto`. The owner can name `display`
`auto`, and only then does a kept draft land without asking.

## 6. The load budget

**What is measured.** These are the numbers the budget is held to:

- Owner item 2: on :8796, a fanned projection (`/api/series?…&replay=1&fan=1`) took 3.5 s, and the live factory
  answered nothing in 60 s.
- `docs/proposals/scale.md`, the page server's answers after its fixes (`scale_bench.py api`, synthetic models of N
  systems, load average 10 to 18): `graph` 0.093 s at N = 10, 0.413 s at N = 30, 2.45 s at N = 100; `loops` (the
  snapshot behind every answer) 0.058 s, 0.32 s and 2.26 s; `status` still 12.7 s at N = 10 and 129 s at N = 30 on
  its first answer, because it runs `check`'s extreme-conditions tests. `items` took 0.005 to 0.5 s at N = 10 to 100
  and 2.5 s at N = 300 (its earlier table, not re-timed after the fixes).
- What did not improve: the browser's layout and routing. An open Diagram at N = 10 drew in 13.2 s after the fixes
  (15.8 s before), and one system took 12 s to draw and 50 s to route.
- `scale.md` also found that a request is never cancelled: answers the client gave up on kept computing, and every
  graph answer after the first ran past five minutes. The snapshot is now made once per key however many ask
  (`server.py:151-179`), but a live one is kept only 1.5 s, so it is made again for each moment.

No new timings were taken for this proposal. dashboard-page-v1 takes them first, against the fixture below, before
it builds anything else.

**The rules:**

1. **One window per dashboard.** Every panel is read at the dashboard's `since` and `at`. All panels then share one
   snapshot key (`server.py:157`), and the snapshot is made once. A window per panel would make one snapshot per
   window, so it is refused in the format itself (section 1).
2. **One batched read on the shared snapshot.** `GET /api/dashboard?name=NAME|draft=…&since=…&at=…` answers every
   eager panel in one request. The batch never calls `status`, because its first answer runs `check`. How it runs:
   - **The moment.** The handler takes the snapshot once (`snapshot`, `server.py:151`) and names it by a **moment
     key**: `(window, at, model mtime, seq)`, where `seq` is a number the server gives each snapshot it makes. For a
     past `at` the snapshot itself is kept until the model changes; for a live one, `seq` is what tells two
     snapshots of the same window apart, compared for equality, never by time. Every panel of the batch, and every
     retry of a late one, is computed on that one snapshot object, so nothing is answered from another moment.
   - **One deadline for the batch, not one per panel.** The batch has **0.8 s** in all, counted from the request's
     arrival, snapshot included. Its panels run **one after another** on the request's own thread, in declared
     order, each given what is left of the 0.8 s; no thread is started for them. A panel is a pure read of the
     snapshot that checks the deadline between its steps (each series, each item kind, each bucket pass) and stops
     at the first check past it. Panels not started by the deadline, and the one stopped, come back as
     `{"late": true, "moment": KEY}` beside those that answered. So ten panels cost at most 0.8 s of server time
     plus one step, never ten limits added together, and the page draws within the 1 s target (rule 6) whatever is
     late. If the snapshot itself is not ready in 0.8 s, every panel is late and the page shows Loading frames.
   - **Late work, bounded.** A late panel becomes one job on the server's **late pool: 2 threads, at most 16 jobs
     waiting**, both hard maxima fixed in code and not read from config. A job is keyed by its moment key and the
     panel's parameters, so a second request for the same thing joins the job already there. Beyond 16 waiting, a
     job is **refused**: the panel answers `{"late": true, "refused": "busy"}` and the page shows "The server is
     busy" with a **Try again** button, and asks nothing more on its own. One dashboard is at most 24 panels
     (rule 5), so one reader can fill the queue but never grow it.
   - **No work for a reader who has gone.** Each job holds the time its reader last asked for it. The page asks for
     its late panels again every 2 s (one request for all of them); a waiting job not asked for in **6 s** is dropped
     before it starts, and so is every job when its moment key's model mtime changes. A running job checks, between
     its steps, both that it is still wanted and a hard limit of **10 s** of its own; past either it stops and its
     partial work is thrown away. Python threads cannot be killed, so what is promised is exactly this: abandoned
     work stops at its next step, and at most 2 threads are ever doing it. A kind whose read has no steps to check
     between (the diagram's layout) is never a batch panel (rule 4).
   - **A kept result has the moment's key.** A finished job's result is kept **30 s** under its moment key and
     parameters, and handed only to a retry that names the same key. It is drawn with the moment it was read at
     ("as of 12:03:04"), and the page's next ordinary poll asks at a new moment, as for any panel. A retry whose key
     is gone (dropped, expired, or the model changed) is answered by a new batch at a new moment, never by a result
     of another moment shown as now.
3. **Replay and fan panels are lazy and slowly polled.** A panel with `replay` or `fan` is left out of the batch. It
   is asked for only once it scrolls into view, and polled every 60 s, not at the page's few seconds. A past
   moment (`at`) is never polled, because its snapshot is kept until the model changes. At most **4** such panels
   are allowed per dashboard.
4. **A cap on diagram panels.** At most **2** `diagram` panels, each drawn folded by default, because ELK layout and
   routing are what take 12 s and 50 s above. The diagram polls with `have=` (only the values, `server.py:402-404`)
   as the Diagram page does.
5. **A cap on panels.** At most **24** panels, checked at compile time for `dashboards:` and again when a draft is
   read, since a draft is never compiled.
6. **The target.** On :8796, the factory itself: **10 panels, first paint under 1 s.** First paint means every eager
   panel drawn with data or marked late, with the lazy ones as Loading frames. The target is measured against a
   **factory-size fixture**, a record of the factory's shape (its item kinds, about 30 systems' worth of stocks and
   a week of events), made by dashboard-page-v1 because none exists on main. The first measurement is 10 eager
   panels of the kinds the default (section 8) makes, cold and then warm, with the result in that gap's record.
   Missing the target is reported with its numbers, and the panel cap or the batch deadline is lowered to meet it. The
   target itself is not raised.

## 7. Layout and editing

**Layout.** A CSS grid of 12 columns at desktop: `s` takes 4 columns, `m` 6, `l` 8 and `full` 12, with rows of a
fixed height and `tall` taking two. Below 700 px (`SPLIT_NARROW`, `split.js:14`) it is one column, in declared
order. Charts are styled only with the design tokens, as charts.md requires. Each panel has four states:

- **Loading**: its frame and title, and "Loading" in words.
- **Empty**: the reason, in the panel's own terms ("No ticket finished in the last day", "stock.backlog: nothing
  recorded in the window").
- **Late**: "Still reading; asking again", until the retry answers, or "The server is busy" with **Try again**
  when the late pool refused it (section 6, rule 2).
- **Drawn.**

A panel whose refs no longer exist after a model edit says so ("stock.x: not in the model") and keeps its place.
That is the same check the compiler makes, done here because a draft is never compiled.

**Editing (story H5).** An **Edit** button turns editing on. Every change goes to the draft (the address and
localStorage) and never to the server. With editing on, each panel is one focusable region with a small toolbar
(Move, Resize, Remove):

- **Move**: Alt+Arrow keys move the focused panel one place earlier or later.
- **Resize**: Shift+Alt+Arrow keys step through `s`, `m`, `l` and `full`, and to and from `tall`.
- **Remove**: the Delete key, or the toolbar's Remove. Focus goes to the next panel, else the one before it, else
  **Add panel**.
- **Add panel**: opens a dialog. It names the kinds and asks each kind's parameters with the controls the full view
  already uses (the Items page's kind and state pickers, the diagram's part picker). On Add, focus goes to the new
  panel. On Escape, focus goes back to the button.

Every move and resize is announced through an `aria-live` region ("Backlog: moved to place 3 of 8"). Mouse dragging
is the same operations, never an extra path. **Done** leaves editing. **Keep** files the display proposal (section
5), and **Copy link** copies the address.

## 8. Defaults, navigation, snapshots and longer windows

**The default, when the model declares no dashboard.** The default is made from what the model declares, never
added of ergostat's own accord:

1. the `goals` panel;
2. one `chart` per system box's measures (its `show:`, else its goals' measures), with `replay`;
3. one `states` and one `cycle-time` panel per item kind;
4. a `note` saying that this is the default and how to keep another.

This stops at the panel cap, in model order. With one dashboard declared, it opens instead. With several, the first
declared opens, and a menu lists the others.

**Navigation.** A **Dashboard** link at `/dashboard` sits in the header after Items (`index.html:13`), never first.
`/dashboard` joins `OTHER_PAGES` in `split.js:26`, so the split pane does not take it for a diagram.

**Snapshot and export (R10).** The page snapshot (`web/snapshot.py`) writes every answer the page would ask for,
keyed as the page keys them (`snapshot.key`). For a dashboard that is the batched answer plus each lazy panel's
answer, fetched at snapshot time within the same deadline and late pool. A panel still late is written as late and says
so offline. The dashboard's export is that one file. A `diagram` panel also keeps the Diagram's SVG export
(`standaloneSvg`, `export.js:7`). There is no other export format.

**Windows longer than 7 days.** The window menu stops at 7d (`main.js:7`), though the server takes any duration
(`_window`, `server.py:245`). A dashboard may open with a longer window (`window: 30d`). The menu then offers it,
and only up to the model's `keep:`, since the record is kept no longer than that. A window longer than `keep:` is
refused at compile time. Series stay bucketed to the same number of points, so a chart's cost grows only with the
record read. dashboard-page-v1 measures 30d on the fixture. A panel past the batch deadline is late, as in section 6.

**The Goals page.** Whether it folds into the Dashboard is left to goals-page-keep-or-fold-decision. Nothing here
depends on the answer: the `goals` panel is the same `goalRow` either way.

## Worked example: software-factory

`examples/software-factory` has item kinds `ticket` (open, doing, review, merged, live, dropped), `pr` and `release`.
Its stocks include `backlog` (intake), `in-review` and `awaiting-deploy` (delivery), and `users` and `bugs-live`
(product). Its goals include `backlog-clear`, `reviews-done`, `all-live` and `no-live-bugs`. A reader asking "why
is delivery slow this week?" would build this dashboard:

```yaml
dashboards:
  delivery:
    title: Delivery, this week
    window: 7d
    panels:
      - {panel: goals, size: full}
      - {panel: states, kind: ticket, size: l, note: "Where tickets wait"}
      - {panel: cycle-time, kind: ticket, size: s}
      - {panel: chart, title: Backlog and review, refs: [stock.backlog, stock.in-review], replay: true, fan: true, size: m}
      - {panel: xy, refs: [stock.in-review, flow.merged], size: m, note: "Does review keep up as it fills?"}
      - {panel: items, kind: ticket, state: review, size: m}
      - {panel: scope, goal: reviews-done, size: m}
      - {panel: diagram, view: dynamics, system: delivery, size: full}
```

Every parameter is sent as written: `kind: ticket` becomes `/api/items-flow?kind=ticket`, and the `items` panel's
title links to `/items?kind=ticket&state=review`. The two lazy
panels are the chart with replay and fan and the diagram; the batch answers the other six. The `states` panel shows
tickets piling up in `review`, with the balance beside it (submissions outrunning merges over the week). The
`xy` panel shows whether the merge rate rises as `in-review` fills, the measured trajectory beside the replay's. The
`scope` shows `reviews-done` against its hold, with the loop's time off.

## Worked example: ticket-factory

`examples/ticket-factory` moves a `ticket` through fourteen states (`new`, `picked`, `located`, `worked`,
`pr-open`, `review-asked`, `changes-asked`, `approved`, `sailed`, `ci-failed`, `ci-green`, `merged`, then `done` or
`stopped`; `examples/ticket-factory/ticket.yaml:28`). Its oversight system measures `actions-waiting`, `ai-spend`
and `cycle-hours`, with goals `nothing-awaits-approval` and `none-stopped`. The reader's question is "where does a
ticket's hour go?". This one is a draft, never declared, shared by Copy link:

```json
{"title": "Where a ticket's hour goes", "panels": [
  {"panel": "goals", "size": "full"},
  {"panel": "heatmap", "kind": "ticket", "size": "l", "note": "Long tails by day"},
  {"panel": "cycle-time", "kind": "ticket", "size": "s"},
  {"panel": "chart", "refs": ["stock.actions-waiting", "flow.approvals"], "replay": true, "size": "m"},
  {"panel": "timeline", "kinds": "ticket", "size": "m"},
  {"panel": "items", "kind": "ticket", "state": "stopped", "size": "m"},
  {"panel": "note", "text": "Approvals were 34-42% of a ticket's time offline (latency.md).", "size": "m"}]}
```

It opens as `/dashboard?draft=eyJ0aXRsZSI6…&since=1d`. The heatmap shows the tail of tickets taking hours, with
the estimate's p90 drawn across it. The chart shows `actions-waiting` against its replay, which is where the
approvals queue shows.

## 9. The follow-on gaps

Each gap is confirmed, with the amendments this proposal makes, in the order they land:

1. **dashboard-page-v1 (confirmed, amended).** It covers the `/dashboard` route, nav and `split.js` entry, the
   grid, the four panel states, drafts in the address and localStorage, the default (section 8), and the kinds that
   reuse a function as it is: `note`, `goals`, `items`, `states`, `cycle-time`, `chart`, `scope`, `items-graph` and
   `timeline`. It includes the batched `GET /api/dashboard` with the batch deadline, the snapshot's `seq` and moment key, the bounded late pool and the caps
   (section 6), the factory-size fixture, and the measurement of the target. *Amended:* it depends on the gap that
   lands `goalrow.js`, `state.goals_off` and `word`. The batched read moves here from dashboard-declaration-and-api,
   because the budget cannot be measured without it.
2. **dashboard-declaration-and-api (confirmed, amended).** It covers `dashboards:` in the compiler (keys, refs,
   caps, `bad-dashboard`), outside the structure fingerprint, `/dashboard/NAME`, SPEC (a section after §4a) and the
   agent guide, and windows past 7d up to `keep:`. *Amended:* it no longer carries the batched read.
3. **dashboard-xy-and-heatmap-panels (confirmed).** It adds the two **new** kinds with their analysis readings
   (section 3), each with a browser test that breaks when the reading is left out.
4. **dashboard-diagram-panel (confirmed, amended).** It makes `drawGraph` and its callers draw into a state passed
   in, not the global `S`, so two diagrams can share one page without the iframe. It also adds the cap of 2 and the
   `have=` polling. *Amended:* if moving off `S` costs more than its budget, the panel is the `?pane=1` frame that
   `split.js` already uses, with the same cap, and that is the most reversible fallback.
5. **dashboard-add-and-edit-draft (confirmed).** It covers Edit, Add, Move, Resize and Remove by keyboard with focus
   returned and announced (section 7, story H5), and Copy link. It changes the draft only.
6. **dashboard-keep-display-proposal (confirmed, held).** It adds the `display` kind of `ergostat.model-change`,
   Keep, and acceptance through `numbers_api.post` with no judge's replay (section 5). It is not started until the
   owner answers the question above. If the answer is "the address and the browser only", it is dropped, and so is
   the declaring half of dashboard-declaration-and-api.
