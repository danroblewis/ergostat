# Preact + htm: component design for the web UI

This is the design the shared components follow (the coordinator's measured inventory of the old pages, put here
by the preact-components gap as its definition asked). What is built so far, and how to use each part, is in
[frontend.md](frontend.md), "Components". Where what was built differs from the design (the folder is
`app/components/`, not `app/ui/`; the side panel keeps the old frame), frontend.md and the gap's record
(`dev/records/preact-components.md`, "Where it stopped") say so.

Read-only research at `origin/main` abd68bb (2026-11-24). Our code under `ergostat/web/static` (vendored ELK,
highlight, marked, uPlot, libavoid left out) is **20,742 code lines** there; `baseline.json` (f6dcc0fa) says
20,687. Measured numbers come from grep counts and line ranges in that tree; anything marked *est.* is an estimate.

The aim is the owner's: a small amount of good, reusable code. That means about twenty parts, each with a few
props, which the nine page moves compose. A page should not need to write its own table, loader, poller, chip,
toggle or link.

---

## 1. Inventory: what repeats today

Counts are occurrences of the pattern in our JS (the regex is in brackets). "Per copy" is the number of lines one
use costs today, read from the cited functions.

| Pattern | Count, where | Per copy today | Notes |
|---|---|---|---|
| **Page scaffold**: `page()`, a box saying "Loading…", `answers()`, `tick(force)`, `ans.begin()`, `if (!force && !ans.changed) return`, `await tick(); S.timer = poll(...)` | `answers()` ×8: pages.js pageLoops, pageAgents, pageRecord, pageItems, pageItem; agent.js pageAgent; kinds.js pageKinds. `poll(` ×14 call sites: pages ×7, agent, dashboard (dashPoll), diagram, itemsets, kinds, main | ~9–12 lines | The same nine lines in every page. pageItems adds its own abort and busy logic (`refresh`, pages.js:759–766). |
| **Stale-answer guards**: `isConnected`, `n !== DASH.page`, `late()`, `gone()`, `S.opens ===` | 67 in all: pages 13, dashboard 8, diagram 8, agent 2, dynamics 2 … | 1–3 lines each | Effect cleanup and abort make these unnecessary. Dashboard: `dashLeave` (dashboard.js:1488–1507, 20 lines) is a hand-written unmount. |
| **Refresh-in-place machinery**: `patch`, `live`, `keep`, `sig`, `holdStill` | `patch(` ×46 (pages 31); `live(`/`keep(` ×24; sig/graphSig ×74; util.js patch/patchKids/patchNode/live/holdStill (util.js:82–200, ~110 lines) | 2–6 lines per use | Preact's keyed diff replaces patch, patchKids and live. Keeping a node across refreshes becomes a component with stable props. |
| **Data tables**: `table(`, `headRow(`, `h("table"`, `table-wrap` | 75: pages 31, details 16, review 6, itemsets 5, equations 4, control, process, blocks, dynamics, panels, reports, kindpage | Head 3–6 lines; whole table 12–30 | Copies: pages.js `table` (one-line helper); pageAgents (pages.js:112–137, 26 lines, grouped tbody plus a total row); daemons (pages.js:140–152); details.js `eventsTable` (445–458); itemsets.js `itemsSection` (~15); `remoteSection`; pageCheck tables; control.js `loopTable`; equations.js `calibrationTable`, `parameterTable`; review.js `paramRows`, `loopRows`. |
| **Sortable columns** | 4 (`data-sort`/`aria-sort`): util.headRow, pageItems (sorted on the server, `sort=KIND:-field`), panels.js legend | ~15 lines in pageItems | Rare. Table takes a `sort` prop: `{by, dir, onSort}` (the server's or the client's). |
| **Clickable rows** (`rowLink`, `class: "click"`) | rowLink ×3 (pages), `click` ×5 | 2–4 | Becomes Table's `rowHref` and `onRow`. |
| **Filter bar**: search box, chips, view toggles | `class: "filters"` ×3 (pageRecord, pageItems, pageKinds); text/search inputs ×22 (pages 8, panel-editor 5) | 6–15 | pageRecord builds its own filter, Enter-to-run and "clear" link (pages.js:168–200). |
| **Segmented toggles** (`seg`, `aria-pressed`) | 35: pages 10, diagram 7, plots-dist 5, kinds 4, relations 3, charts 2 … | 3–8 | The `seg()` helper is written twice, the same each time: pages.js pageItems (~872) and diagram.js pageDiagram pmBar. `finSeg` (pages.js:690–696) is a third version written out by hand. |
| **Menus** (`menu(`) | util.js menu (25 lines); used by main.js whenMenu, diagram.js "⋯" more, dashboard.js dashHead refresh | 10–30 per use | Already parameterized: `{label, checked, hint, onclick, sep}`. Ports as it is. |
| **Selects** | `h("select"` ×14: panel-editor 8 (`fillSelect`, `radios`, `field`), dashboard dashVarsBar, diagram sysSel, pages 3 | 4–10 | |
| **State words and chips** | `statusEl`/`stateWord`/`goalWord`/`s-holding`/`s-off` ×63: pages 18, details 17, blocks 6, goalrow 6, diagram 4 …; `stbox`/`set-chip` ×11 (kinds.kindBar chip, remoteSection, pageItems chip) | 1–5 | Three spellings of one idea: statusEl (util:131), stateWord (pages:612) and the stbox chip (kinds.js kindBar). |
| **Links to things** | item ×52 (pages 24, itemsets 10, details 6), agent ×23 (`agentA`, `agentLink`, `agentHref`), kind ×16 (`kindHref`, `partLink`, `partHref`), plus `remoteItemLink`, `eventItemLink`, review `toolLink` | 1–3 | Four helpers in details.js (agentA, agentLink, partLink, itemLink, 429–437) and two in pages.js. A plain click opens the side panel; a modified click opens a new tab. That rule is written out in `plainClick` and `rowLink`. |
| **Number with unit** (`fmt`, `dur`, `ago`, `usd`, `rateText`, `tokensText`, `cpuText`, `bytesText`, `stamp`) | 291 call sites: details 59, pages 59, control 56, charts 26 … | inline | The formatters are good and stay as functions (util.js:203–320, ~110 lines). Only the "title shows the exact value" wrapper repeats. |
| **Sections with a heading**, folds | `h2/h3` ×136 (pages 49, details 23, panel-editor 12, dynamics 11); `details/summary` ×66 (pages 20, diagram 18); `section` ×16; disclose/fold/aria-expanded ×142 | 2–5 | pageAgent's `sec()` (agent.js:163), kindBar's disclosure (kinds.js:20–22), pageItems' folded systems (`foldedSystems`, `rememberFolded`, pages.js:617–623), dashRowCell toggle (dashboard.js:712–726). |
| **Label/value lists** (`dl`) | `dl(` ×44: details 9, agent 7, dynamics 6, control 4, pages 4, process 4; plus "meta" pairs in pageItem and pageAgent (`pair`, written twice) | 1–3 | |
| **Notes, muted text, empty states** | `class: "note"` ×58, `muted` ×371, "Nothing …/yet" ×49 | 1–3 | pageRecord's `empty()` (filter miss plus clear) is the best version, and it lives on one page only. |
| **Loading and error** | "Loading…" ×19 (details 7: `panelLoading`; pages 4; dynamics 3; diagram 2); "could not be read" ~10; `catch` ×152 | 2–4 | Each opener does `panelLoading` → `try api` → `note.textContent = "Could not be read."` (details.js:130–132, 211–212, 320–322). |
| **Slow answers made visible** | Only the dashboard does it: `dashSayLate`, `DASH_LATE`, `DASH_GIVE_UP`, (dashboard.js:864–911, ~45 lines) | 45 | Every other page just waits. This should become generic. |
| **Side panel** (`#detail`) | `showDetail`/`openNode`/`openLoop`/`openAgent`/`openEdge`/`openSystem` ×51: details 25, dynamics 9, diagram 6, blocks 3 | head and close 15 lines once (details.js:14–31) | Every opener builds `kind`, `h2` and body. `askedAgain` and `S.again` re-open it when the window changes. |
| **Sparklines** | 3 implementations: details.js `sparkSvg` (13), charts.js `sparkPath` (13), panels.js `spark` (22); dynamics.js `sdSparks` draws into the diagram (separate) | 13–22 | goalrow.js `spark` cell, dashboard stat panels, the diagram side list. |
| **uPlot charts** | `uPlot`/`mountPlot`/`lineChart` ×46: charts 22, panels 9, control 8 (`chartBox`, `stepChart`, `bodeCharts`), review 4 | mount/sync/destroy ~30 in charts.js (`sweepPlots`, `mountPlot`, `chartGroup`), plus chartPanel lifecycle | panels.js `chartPanel` is 640 lines (456–1097). About a third of it is the frame: head, legend, state message, resize. |
| **Code and query boxes** | promql.js `make` (~100), sql.js `make` (~89); 80% the same (diff: 101 changed lines of 190); codebox.js (38) shared | ~70 duplicated | One CodeEditor with a language adapter `{tokens, context}`. |
| **Dialogs** | panel-editor.js ×2 (`pe-overlay` 1018, `pe-pick` 852) | ~20 each (focus, Esc, backdrop) | Only the panel editor. |
| **Trees and graphs** | relations.js (graph and timeline), process.js, the diagram views; no generic tree | n/a | Drawing, not chrome. Wrapped, not rewritten. |
| **Split panes** | split.js (148: grips, peer window, splitLayout), diagram only | n/a | Stays the diagram's. |
| **Keyboard** | keydown ×23: relations 6 (Enter on role=link nodes), dashboard 3 (`dashKeydown`), promql/sql 2+2, colours (hold C), keys.js (diagram roving focus), main/util Escape | 2–30 | The global Escape is handled twice (main.js shutDetail, util closeMenus). |
| **Polling** | util.js `poll` (20 lines, good semantics: after-finish, hidden tab, `{wait}`), dashboard `dashPoll`/`dashEvery`, itemsets/kinds own intervals (`flowsAt` 30 s, `gpsAt` 10 s caches in pageItems) | 2 per use plus ad-hoc caches ~10 | |
| **Address state** (`setQuery`, `replaceRoute`) | 23: dashboard 7, util 6, pages 3 … pageItems `go()` (pages.js:767–787, 21 lines) rebuilds the query by hand | 3–20 | |
| **localStorage** with try/catch | 29: diagram 11, dashboard 7, pages 5, charts, colours, split | 2–3 | |
| **Pointer drag** | pointerdown/move ×31: dashboard 5 (grid drag), diagram, interact, relations, split | n/a | Domain-specific. Not generalized. |

Totals: `h(` is called 2,334 times (pages.js 727) and `s(` (SVG) 420 times (diagram 120, blocks 79,
relations 78, dynamics 54). The SVG calls are drawing and stay inside wrapped components.

---

## 2. The component set

The rules for this set:

- One file per component under `app/ui/`, each under ~120 lines.
- Props are data plus callbacks.
- No component fetches, except `Async`, which shows a `useApi` result.
- A domain component is a configuration of a generic one: column sets for Table, tones for Chip. Never a parallel
  widget.

### 2.1 Foundation (`app/core.js`, the foundation gap)

| Export | What it is | Replaces |
|---|---|---|
| `api`, `apiPost`, `apiSend` | Today's fetch layer, unchanged in behaviour: snapshot lookup, window params, token header. Each call is recorded in the store's request log (path, ms, status, aborted). | util.js apiText/api/apiPost/apiSend (util.js:384–436) |
| `store` + `useStore(sel)` | A tiny subscribe store: `createContext` plus a `useStore` that re-renders on a selected slice. | the global `S` (page-wide parts only, see §3) |
| `Router`, `useRoute()`, `navigate`, `useQueryState(key, default, {parse, write})` | The path, the query and the link-click capture from util.js. `useQueryState` reads and writes one query key with replaceState. | util.js currentRoute…route (util.js:559–679), pageItems `go()`, setQuery users |
| `AppShell` | Header (brand, project select, run state, "N for you", nav with `aria-current`, window picker), `<main>`, `<SidePanel>` | index.html header, main.js, util.js refreshHeader/refreshProjects |
| `format.js` | `fmt dur ago usd rateText tokensText cpuText bytesText stamp shareText op holdText`, moved as they are | util.js:203–320 |
| `Dom` | `<Dom node={el}/>` or `<Dom make={(el) => cleanup}/>`: mounts an imperative node and calls its cleanup on unmount. **The migration bridge**: legacy panels inside Preact, drawing engines inside components. | `live()`, the x-live stubs |

### 2.2 Hooks

| Hook | Signature | Notes |
|---|---|---|
| `useApi` | `useApi(path, params, {every, keep, enabled}) → {data, error, loading, slow, ms, reload}` | One AbortController per instance, aborted on unmount and on a change of `path` or `params`. Keeps the last good `data` while the next request is in flight. Text-compares each answer, as `answers()` does, so an unchanged poll sets no state and draws nothing. `slow` goes true after 1.5 s *est.* with nothing back. `every` polls through `usePoll`. Replaces answers(), tick, the stale guards and dashSayLate's generic part. |
| `usePoll` | `usePoll(fn, ms, {enabled})` | Today's `poll` semantics: the next run starts after this one finishes, nothing runs while the tab is hidden (it runs at once when the tab shows again), `{wait}` from fn sets the next wait, `ERGOSTAT_POLL_SPEED` applies. Stops on unmount. |
| `useWindow` | `() → {since, at, live, setSince, setAt, words}` | From the store. `useApi` adds `since`/`at` by default; `{keep: true}` opts out (the header's calls, the dashboard's own window). |
| `useSelection` | `(key = "select") → {sel:Set, toggle, set, clear}` | Kept in the address (`?select=`). Opening the side panel reads it. |
| `useKeys` | `useKeys({"Escape": fn, "mod+Enter": fn}, {when, target})` | One document listener stack. The innermost handler wins, so the panel's Escape before the page's. Replaces main.js and util.js Escape, the promql/sql Ctrl+Enter and Ctrl+Space, and dashKeydown's arrows. |
| `useStored` | `(key, default) → [v, set]` | localStorage with try/catch (29 sites). |

`useHoldStill` stays inside Table (the `hold` prop). It is not a public hook.

### 2.3 Generic components (12)

| Component | Props | Renders | Replaces |
|---|---|---|---|
| `Table` | `columns:[{key, head, num?, title?, cell(row), sort?}]`, `rows`, `rowKey`, `caption`, `groups?:[{key, head, rows}]`, `total?`, `rowHref?`, `onRow?`, `sort?:{by, dir, onSort}`, `empty?`, `hold?` | `.table-wrap > table` with sr-only caption, `th scope=col`, `aria-sort`, grouped tbodies, a total row, keyed rows (`data-row`), and hold-still with "N updates waiting" | pages.table, util headRow/tableCaption/rowLink/holdStill, the hand-built tables in pageAgents, daemons, eventsTable, itemsSection, remoteSection, pageCheck, control.loopTable, equations tables, review rows |
| `Async` | `of` (a useApi result), `children(data)`, `empty?`, `loading?` (words), `what?` (for messages) | The children once there is data. "Loading…" only on the first load. "Still waiting for {what} (4 s)" when `slow`. "{what} could not be read: …" with a Retry button on error, keeping the old data under it. The `empty` text and action when data is empty. | 19 Loading, ~10 could-not-be-read, panelLoading, pageRecord `empty()`, dashSayLate wording |
| `Section` | `title`, `level=2`, `aside?` (count, muted words), `actions?`, `fold?:{key?, open?}`, `id?` | `section > hN` (or `details > summary` when folded). The fold state is remembered by `key` through useStored. | agent.js `sec`, kindBar disclosure, foldedSystems/rememberFolded, dashRowCell fold, the 136 h2/h3 plus 66 details sites where they head a block |
| `Facts` | `pairs:[[label, value]]`, `inline?` | A `dl`, or the inline "meta" line. Null and empty values are dropped. | details.js `dl`, pageItem and pageAgent `pair`, pageCheck counts |
| `Note` | `tone: "muted" \| "note" \| "warn" \| "bad"`, `children`, `action?:{label, onClick \| href}` | One `p` with the right class | note, muted, att, lvl-* paragraphs |
| `Chip` | `label`, `n?`, `tone?`, `on?`, `href?`, `onClick?`, `onRemove?`, `title?` | A count-and-word box, a link or a button, with an optional × | kindBar `chip`, stbox, set-chip, remote counts, statusEl |
| `Segmented` | `label`, `options:[{value, label, title?}]`, `value`, `onChange` | `span.seg[role=group]` of buttons with `aria-pressed` | both `seg()` copies, finSeg, diagram pmBar, kinds "all states", plots-dist toggles |
| `Menu` | `label`, `items` (array or `() => array`, as today), `right?`, `up?`, `title?` | Button plus popover. Closes on outside click and Escape. The first item takes focus. | util.js menu, used as it is by window picker, diagram ⋯, dashboard refresh |
| `Field` | `label`, `kind: "select" \| "search" \| "text" \| "check" \| "range" \| "radio"`, `value`, `onChange`, `options?`, `multi?`, `debounce?`, `onEnter?` | A labelled control | panel-editor field/fillSelect/radios, dashVarsBar selects, pageRecord and pageItems search, diagram sysSel and paths slider |
| `Dialog` | `label`, `open`, `onClose`, `children` | Overlay with `role=dialog aria-modal`, focus trap, Escape | panel-editor pe-overlay and pe-pick |
| `Spark` | `values`, `w`, `h`, `setpoint?`, `fill?`, `color?`, `axis?` | An inline SVG path with gaps where values are null | sparkSvg, sparkPath, panels.js spark |
| `UPlot` | `opts`, `data`, `group?` (cursor sync), `onCursor?`, `height` | Mounts and destroys uPlot, resizes on container width, joins a sync group | charts.js mountPlot/sweepPlots/chartGroup, control.js chartBox, chartPanel's plot lifecycle |

Not in the starting set: a general `Tree` (no generic tree exists) and a general `Split` (split.js serves only the
diagram). Each is added by the first page that needs one.

### 2.4 Domain components (7), built from the generic ones

| Component | Built from | Replaces |
|---|---|---|
| `Ref` | a plain `<a href>`. `to: "item" \| "kind" \| "agent" \| "goal" \| "part" \| "event"`, `id`, `remote?`, `panel?`. A plain click with `panel` set opens the SidePanel; a modified click is left to the browser. | itemLink, partLink, agentA, agentLink, kindHref links, remoteItemLink, eventItemLink, review toolLink, plainClick (~91 sites) |
| `StateChip` | Chip. `word` (goal word or item state), with the tone from one table: off=bad, stale/open=warn, holding=quiet, none="–". | statusEl, stateWord, goalWord display, s-holding/s-off spans, coherence s-open |
| `goalColumns(names, {open})` | Column definitions for Table, one per GOAL_CELLS entry: StateChip, Spark, `format`. | goalrow.js GOAL_CELLS; used by Goals, the side list and system panels |
| `itemColumns(names, {kind})` | Column definitions: id (Ref), title, state (StateChip), in-state `dur`, lease, eta, moved-at. | the item rows in pageItems kind tables, itemsSection, remoteSection, eventItems, review |
| `EventsTable` | Table plus `eventColumns`. `fold` groups runs of the same event; a row click opens the event in the SidePanel. | details.js eventsTable/showRun/showEvent/dataCell; Record, item history, side panels |
| `SeriesChart` | UPlot plus charts.js option builders (`baseOpts`, `underlay`, fan, off-hatch), kept as functions. Props `series, setpoint, off, fan, whatif`. | charts.js lineChart users (side charts, loop scope, useChart, flowChart, cycleChart) |
| `ChartPanel` | Section (head: title, unit, state) plus SeriesChart or a plot form from the plots registry, legend, and the state message through Async wording. | panels.js chartPanel's frame. Its value formatting and readers (`readAnswer`, `formatValue`, `axisLabels`) move as plain functions. |

`KindBar` (kinds.js) stays a small page-local component: Section plus Chips. It is used only on the Items pages.

### 2.5 Layout (3)

| Component | What |
|---|---|
| `Page` | `title`, `aside?` (e.g. "· goals off 2"), `toolbar?` (a `.filters` row), `children`. Replaces `page()` and each page's hand-made filter row. |
| `SidePanel` | Reads `store.panel = {kind, title, render}`. Head (kind, title, ×), Escape through useKeys, focus to its heading when it was opened by keyboard, scroll to top, "About this" folds last. `openPanel({kind, title, body})` is the one opener; legacy openers pass DOM through `Dom`. Replaces showDetail, closeDetail, shutDetail, panelLoading, askedAgain/S.again (it re-renders when the window changes because its body uses useApi). |
| `Canvas` | Wraps the diagram engines: takes `graph`, `view`, `sel`; calls `drawGraph`, `drawBlocksView`, `drawProcessView` and `relGraph` into its SVG through `Dom`; pan/zoom (interact.js) attached in an effect. The SVG drawing (`s(`, 420 calls) is not rewritten. |

The full set: 6 foundation exports, 6 hooks, 12 generic, 7 domain and 3 layout parts.

### 2.6 Three pages composed

**Goals** (today pages.js pageLoops 45–78 plus goalrow.js; 34 + 33 code lines):

```js
function Goals() {
  const [sel, setSel] = useQueryState("select", "");
  const loops = useApi("loops", { perf: 1 }, { every: 3000 });
  const systems = useApi("systems", {}, { every: 3000 });
  useEffect(() => { if (sel) openGoal(sel); }, [sel]);
  return html`<${Page} title="Goals" aside=${html`<${GoalsOff}/>`}>
    ${(systems.data || []).filter((s) => s.quiet).map((s) => html`<${Note} key=${s.name}><b>${s.name}</b>: ${s.quiet}<//>`)}
    <${Async} of=${loops} what="the goals">${(d) => html`
      <${Table} caption="Goals" rows=${rankGoals(d)} rowKey="name" onRow=${(g) => setSel(g.name)}
        columns=${goalColumns(["goal","status","measure","value","bound","far","timeOff","backIn","spark","performance","acted","card"])}/>`}
    <//>
    <${Note}>${timeOffCaption()}<//>
  <//>`;
}
```

That is about 20 lines against 34. The `steadyWord` hysteresis (pages.js:23–43) moves as a function.

**Record** (pages.js pageRecord 164–216, 50 code lines):

```js
function Record() {
  const [match, setMatch] = useQueryState("match", "");
  const [runs, setRuns] = useQueryState("runs", "", { parse: (v) => v === "1" });
  const scope = useRecordScope();               // machine, item, about, from, to, remote, window=1 from the query
  const evs = useApi("events", { n: 80, match, runs: runs ? 1 : "", ...scope.params }, { every: 3000 });
  return html`<${Page} title="Record" toolbar=${html`
      <${Field} kind="search" label="Event type, item or source" value=${match} onEnter=${setMatch}/>
      <${ScopeLine} scope=${scope}/> <${Field} kind="check" label="Show runs" value=${runs} onChange=${setRuns}/>`}>
    <${Async} of=${evs} what="the record"
      empty=${match ? { text: `Nothing matches “${match}”`, action: { label: "clear", onClick: () => setMatch("") } } : "Nothing recorded yet."}>
      ${(d) => html`<${EventsTable} events=${d.events ?? d} fold/>`}
    <//>
  <//>`;
}
```

About 25 lines. The remote branch (`remoteApi`/`remoteSaid`) becomes the `Async` error wording plus one
`Note`, because `useApi` returns `{error}` instead of `{failed, why}`.

**Agents** (pages.js pageAgents 80–162, 80 code lines; the densest table on any page):

```js
function Agents() {
  const agents = useApi("agents", {}, { every: 3000 }), daemons = useApi("daemons", {}, { every: 3000 });
  return html`<${Page} title="Agents">
    <${Async} of=${agents} what="the agents">${(a) => html`
      <${Ladder} agents=${a}/>
      <${Table} caption="Agents, by rung" hold rowKey="name" rowHref=${(r) => agentHref(r.name)}
        groups=${byRung(a)} columns=${agentColumns(a)} total=${agentTotals(a)}/>
      <${Note}>${costCaption()}<//>`}<//>
    <${Async} of=${daemons}>${(d) => Object.keys(d).length ? html`
      <${Section} title="Daemons" level=3><${Table} caption="Daemons" rows=${Object.entries(d)} columns=${daemonColumns}/><//>` : null}<//>
  <//>`;
}
```

`agentColumns` holds the exception, cost and use cells (~30 lines, data only), so the page is about 45 lines
against 80. Most of the saving is the table head, the total row, holdStill and the scaffold.

The Item page (pageItem, 145 lines) follows the same shape: `Facts inline` for the meta line, `Section` for each
part, `EventsTable` for history. The Dashboard keeps its grid (`DashGrid`, its layout maths unchanged) and draws
`ChartPanel` cells. Its head is a `Page` toolbar of buttons, `Menu` and `Field`; `dashLeave` becomes effect
cleanup.

---

## 3. State and data flow

**Shared store** (page-wide, small):

| Slice | Contents | Written by |
|---|---|---|
| `window` | `{since, at}` | header picker; Router from `?window=` |
| `status` | last `/api/status` (run state, loops, attention, rate_units, first, window) | AppShell, polled every 5 s with `keep` (not aborted by pages) |
| `route` | `{path, q}` | Router (popstate, link capture) |
| `panel` | `{kind, title, body, key}` or null | `openPanel`, `closePanel`, route change (unless keep) |
| `sel` | the selected parts (mirrored to `?select=`) | useSelection, diagram clicks |
| `requests` | ring buffer of the last 100 calls: `{path, ms, status, aborted, at}`, and the count in flight | `api` |
| `snap` | the SNAPSHOT object, or null | boot |

Nothing else goes in the store: graph layout state (`S.layout`, `S.view`, `S.pins`, `S.portAt`), dashboard drafts
and editor state stay in their page. They are page state, `useRef` for what the engines mutate.

**Page state:** each page's data comes from its own `useApi` calls. Choices that belong in the address (filters,
view, sort, page, fin) live in `useQueryState`, so a pasted link opens the same view. That is today's behaviour,
written once. Choices that only make sense locally (folded systems, chart picks, refresh rate) use `useStored`.

**Polling:** `useApi(..., {every})` uses `usePoll`. The next request starts only after the last one finishes,
nothing runs in a hidden tab, and a hidden tab that shows again runs at once. Slow kinds of data keep their own
interval instead of the cache maps pageItems builds by hand (`flowsAt` 30 s, `gpsAt` 10 s): `useApi("items-flow",
…, {every: 30000})`.

**Abort:** every `useApi` owns an AbortController, combined with the route's signal through `AbortSignal.any`. It
aborts on:

1. unmount (leaving the page, closing the panel)
2. a new `path` or `params` (a click asks at once; the older request is dropped and its answer never drawn)
3. `reload()`

An AbortError is swallowed in `useApi`, never set as `error`. This replaces `pageSignal`/`leavePage`, pageItems'
`busy`/`ctl`, `seq`/`late()` in pageItem, and `DASH.ver`/`DASH.page`.

**Slow calls become visible** at three levels:

1. **In place:** `useApi` sets `slow` after a threshold (*est.* 1.5 s). `Async` then says "Still waiting for the
   goals (4 s)" over the last data, instead of a blank "Loading…". This replaces the dashboard's one-off `dashSayLate`.
2. **In the header:** AppShell shows "1 slow" when a call has been in flight more than 5 s *est.*. Its title lists
   path and elapsed time from `store.requests`.
3. **For measurement:** `?timing=1` (or a keyboard toggle) adds a small table under the page: the last calls,
   ms, 200/304/aborted. The same buffer is on `window.ergostat.requests`, so tests and the factory's UI probes can
   read it.

**Refresh without churn:** `useApi` compares answer text (as `answers()` does), so an unchanged poll keeps the same
`data` object and Preact skips the render. Tables are keyed by row id. `Table hold` keeps rows still while the
pointer or focus is in them, as `holdStill` does now.

---

## 4. Styling

`style.css` (1,107 code lines) plus panel-editor.css 118, panels.css 105, dashboard.css 74 and plots.css 30 make
1,434 lines.

**Keep as they are:**

- **Tokens** (style.css:4–104, about 100 lines incl. the dark theme). Every component uses only `var(--…)`.
- **Drawing styles** (about 520 lines *est.*): the diagram's SVG classes (499–735 drawings, process, frames,
  blocks, dynamics), selection and keyboard ring (900–913), correspondence colours (914–933), split (934–1008),
  relations (1098–1146), proposals (1214+), uPlot rules (376–392), plots.css. These style SVG the engines draw, and
  the engines are not rewritten.
- **Panel editor and dashboard grid CSS** (~190): it moves with those components and shrinks slightly once Field
  and Dialog own their controls.

**Replace with a few classes per component** (page chrome, ~450 lines today *est.*: tables 196–230, state
231–239, lists 240–267, chips 268–273, Items-page lists and bars 274–498, agents/items/check 734–811, items'
fields and messages 1058–1092, phone rules 859–895):

| Component | Classes |
|---|---|
| Table | `.table-wrap`, `.t`, `.t-num`, `.t-group`, `.t-total`, `.t-click`, `.t-waiting`, plus the phone card rule (today's Loops `card` column) generalized to `columns[].card` |
| Chip / StateChip | `.chip`, `.chip.on`, `.chip[data-tone=bad\|warn\|quiet]`, `.chip-n`, `.chip-x`; StateChip writes `data-tone` instead of `s-off`/`s-holding`/`lvl-*` |
| Section | `.sec`, `.sec-head`, `.sec-aside`, `.sec-actions` (folds use native `details`) |
| Facts | `.facts`, `.facts.inline` (replaces `.meta`, `.counts`, `.kind-def` dl rules) |
| Note / Async | `.note[data-tone]`, `.async-slow` |
| Segmented / Menu / Field / Dialog | `.seg`, `.menu*` (kept), `.field`, `.dialog` |
| Page / AppShell / SidePanel | `.page`, `.page-head`, `.filters`; `header.bar`, `nav`; `.detail` (kept) |

**Delete:**

- The per-page variants these replace: `.kind-flow .states`, `.stbox`, `.set-chip`, `.ladder-line .exception`,
  `.att > div b.lvl-*`, `.quiet-line`, `.remote-says`, `.hints`, `.page-loading`/`.items-loading`/`.panel-loading`,
  `.waiting`, and the three spark classes merged into one.
- Of panels.css, the head, legend and message rules move to ChartPanel's (≈40 of 105 kept as they are).

The page-chrome CSS goes from about 450 lines to about 220 *est.*. All CSS goes from 1,434 to about 1,150 *est.*.
CSS files stay global sheets, one per area, loaded from index.html. No CSS-in-JS and no build.

---

## 5. Code size after the move (*est.*)

Today by area (code lines at abd68bb, measured), and after (*est.*):

| Area | Files | Today | After *est.* | Why |
|---|---|---|---|---|
| Core, shell, format | util 595, main 63, index.html 77 | 735 | 600 (core 280, format 120, AppShell 120, index 15, Dom/store 65) | patch, patchKids, live and holdStill (~110) go to Preact and Table; the 49 script tags become one module |
| Generic, domain and layout components | (new) | 0 | 900 (12 generic × ~45, 7 domain × ~35, 3 layout × ~40) | |
| Pages chrome | pages 1485, details 505, review 441, agent 164, itemsets 151, kinds 104, kindpage 71, goalrow 33, guide 157, reports 55 | 3,166 | 2,050 | scaffold ×9, tables ×~25, links, loading and error, stale guards, pair/sec/dl helpers, pageItems' query rebuild and abort (pageItems 400 → ~250) |
| Dashboard and editor | dashboard 1488, examples 57, panel-editor 1069, promql 188, sql 145, codebox 38 | 2,985 | 2,350 | dashLeave and the DOM placement and cell map → keyed render (~200); head and vars bar → Page/Menu/Field (~60); a shared CodeEditor (−80); editor fields and dialogs → Field/Dialog (~150); dashSayLate → Async (~40); grid layout maths kept |
| Charts | charts 688, panels 1329, control 335, equations 269 | 2,621 | 2,250 | mount/sync → UPlot (~60); chartPanel frame → ChartPanel/Section (~200); sparks ×3 → 1 (~35); tables in control and equations → Table (~60) |
| Plot forms | plots-* 1,787, frames 129 | 1,916 | 1,860 | canvas renderers kept; only their figure and table wrapper shared |
| Diagram views | diagram 1644, dynamics 1137, blocks 1236, process 456, relations 628 | 5,101 | 4,650 | pageDiagram (290) and renderSide/inbox (~130) → components; the open* panels (dynamics openNodeSD etc.) → SidePanel plus Facts plus Async; the SVG drawing is kept |
| Drawing engines | avoid 730, places 310, layouts 300, satellites 219, untangle 149, routeparts 91, valves 121, graph-layout 6, export 138, colours 94, interact 323, keys 155, split 148 | 2,784 | 2,720 | unchanged except Escape and keys through useKeys, and split's mount |
| CSS | style 1107 + 4 sheets 327 | 1,434 | 1,150 | §4 |
| **Total** | | **20,742** | **≈18,500 (range 17,800–19,300)** | about −11% |

Assumptions:

1. htm templates are about as dense as today's `h()` calls, so syntax alone saves nothing. The savings are
   consolidation.
2. The drawing engines and the plot forms (about 9,800 lines, 47% of today) are wrapped, not rewritten. Rewriting
   them is out of scope, and is where most of the remaining size is.
3. Vendored Preact/htm is excluded, as baseline.json excludes the other libraries.
4. Pages keep every feature they have today; no behaviour is dropped to save lines.

If the diagram's side panels (`openNode`, `openLoop`, `openAgent`, `openEdge` and their SD and blocks versions,
about 900 lines across details, dynamics, blocks and process) are rebuilt on Section, Facts and Async rather than
bridged, another 250–350 lines go. That is the lower end of the range.

What will be measured after each page gap: `metrics.py` code_lines, files over 1,000 lines (today 8; the goal is
pages.js gone and dashboard.js split, leaving 5), and decisions per 100 lines (63.4 today; fewer guards should
lower it).

---

## 6. Build order

**Minimum before any page move** (the foundation gap plus these; about 700 lines *est.*):

1. `core.js`: api with the request log, store, Router with useQueryState and link capture, `Dom` (the bridge both
   ways), `format.js`.
2. Hooks: `usePoll`, `useApi` (abort, unchanged-skip, `slow`), `useWindow`, `useKeys` (Escape at least).
3. `AppShell` (header, nav, window `Menu`, run state) and `Page`.
4. `SidePanel` with `openPanel`, accepting legacy DOM through `Dom`, so the old `open*` functions keep working from
   new pages and the old diagram.
5. `Async`, `Table` (columns, groups, total, rowHref, hold), `Note`, `Section`, `Facts`.
6. `Ref` and `Chip` with `StateChip`. Nearly every page lists links and states.

The legacy pages run under the new shell through `Dom` (route → `<Dom make={(el) => pageX(el, q)}/>`) until each
one moves, so the nine page gaps can land in any order.

**Added by the first page that needs them:**

| Part | First user (suggested order) |
|---|---|
| `goalColumns`, `Spark` | 1. Goals (smallest page; proves Table, poll and the panel) |
| `agentColumns`; `Table` groups and total | 2. Agents |
| `Field` (search, check), `EventsTable` | 3. Record |
| `itemColumns`, `Segmented`, `useSelection`, `useStored` | 4. Items list (pageKinds, pageItems; graph and timeline through `Dom` around relations.js) |
| item `Facts inline`, `Section fold` | 5. Item and kind pages (pageItem, kindpage, kinds, review) |
| `SeriesChart`, `UPlot` | 6. Model, Check and Guide (fit charts), or the side charts if the diagram comes first |
| `Dialog`, `Field` select/radio/multi, `CodeEditor` | 7. Panel editor |
| `ChartPanel`, `Menu` in a toolbar, `DashGrid` | 8. Dashboard |
| `Canvas`, `Split` (moved from split.js) | 9. Diagram (dynamics, blocks and process views; the side panel's own openers) |

**Rules for the page gaps** (to keep the set small):

- A page gap may add a column set or a page-local component freely.
- A new *generic* component, or a new prop on one, needs a second user named in the gap.
- No page writes its own fetch, poll, abort, loading text, table head, chip or link. A reviewer greps for `fetch(`,
  `setTimeout(` and `h("table"` in a page's file.
- Each page gap reports code lines before and after with `metrics.py`.
