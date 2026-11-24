# The web page's code: Preact pages beside the old ones

The page is moving, one page at a time, from hand-built DOM (`h()` in `util.js`, `pages.js` and friends) to Preact
components written with htm. Old and new run side by side on the same page, so the site works at every step.

## What is there

- **The library**: Preact 10 and htm 3.1.1 in one ES module, vendored at
  `ergostat/web/static/vendor/preact/htm-preact-standalone.module.js` (see its README). No other library, no bundler,
  no build step, nothing from the network.
- **The core**, `ergostat/web/static/app/core.js`. Import everything from it, by its absolute path, so there is
  one Preact on the page:

  ```js
  import { html, useState, useEffect, useApi, useStore } from "/static/app/core.js";
  ```

  - It re-exports the vendored module: `h`, `html`, `render`, `Component`, `createContext` and the hooks.
  - `useApi(path, params, { every })` returns `{ data, error, loading, slow, ms, reload }`. It asks
    `/api/PATH?since=WINDOW&at=MOMENT&...params`, again when the path, the params, the window or the moment change.
    When the component goes, the call in flight is aborted. With `every`, it asks again that many ms after each
    answer, through `usePoll`. An answer the same as the last changes nothing (`ms` stays that of the last changed
    answer), so nothing is drawn again. `slow` is when the call on its way began, once it has had nothing back for
    `SLOW_MS` (1.5 s), else 0; the last `data` is kept meanwhile and under an error. Every call is timed into the
    call log.
  - `usePoll(fn, ms, { enabled, deps })` calls `fn(signal)` at once, then again `ms` after it finished, or after
    the `{ wait }` it gives back: never two at once, never faster than twice a second, never while the tab is hidden
    (at once when it is shown again), shortened by `ERGOSTAT_POLL_SPEED`, as the old `poll()`. `ms` 0 calls it once.
    It begins again when `deps` change, and stops, its signal aborted, when they do or the component goes.
  - `apiGet(path, params, signal)` is one timed GET, for a call outside a component's drawing.
  - `store` and `useStore(pick)` hold what every page shares: `window` ("1h"...), `at` (the moment shown, null when
    live), `project` (its name), `status` (the header's answer) and `route` (the top path, "/agents").
    `useStore((s) => s.window)` draws the component again when that value changes. For now the old code writes the
    store: `route()` and `refreshHeader()` in `util.js` call `sync()`.
- **The shell**, `app/shell.js`. It draws the header as components: the project list, the two counts (`Status`:
  the goals off and "N for you", each a link with its wording as its title) and the navigation (`Nav`: the page
  shown marked). Then it calls the old start (`main.js` `startPage`), which fills the project list and the window's
  menu into that header, polls the status and routes the first page. A snapshot, or a page opened from a file,
  loads no ES module. There `main.js` starts by itself on the header that `index.html` carries.
- **The router**, `app/router.js` with `route()` in `util.js`. `route()` keeps what it did: the redirects of old
  addresses, the window in the address, the panel. At the end it asks the router to mount the page's module,
  `app/pages/<page>/index.js`, when that module exports `page`. Otherwise it calls the old function (`pageAgents`,
  `pageItems`...). Leaving a page unmounts it, so its effects end.

  | address | module |
  |---|---|
  | `/diagram` (and any address no page claims) | `diagram` |
  | `/dashboard` | `dashboard` |
  | `/goals` | `goals` |
  | `/agents` | `agents` |
  | `/items`, `/items/KIND` | `items` (`id` is the kind) |
  | `/item/ID` | `item` (`id` is the item's id) |
  | `/record` | `record` |
  | `/model` | `model` |
  | `/check`, `/guide`, `/agent/NAME` | none yet: always the old function |

  `panel-editor` has no address of its own. The Dashboard opens it, and the Dashboard uses what it exports. The
  page component is given `path` (the address's path), `q` (its query, a `URLSearchParams`) and `id`.
- **The timing overlay**, `app/timing.js`. It is off until Shift+T, or until the address carries `?timing=1`
  (which no page reads as part of its query). It lists every API call the page made, slowest first, with its path,
  milliseconds and status. Shift+T closes it again, and Shift+T typed into a field is left to the field. The call
  log is `util.js` `timed`, in `window.ERGOSTAT_CALLS`, the last 500 calls. Both the old pages' calls (`api`,
  `apiPost`, `apiSend`) and `useApi`'s go through it. The fetches the Dashboard and its panels make for themselves
  (`dashboard.js`, `panels.js`, `export.js`) are not in it until those pages move.
- **The budget helper** for browser tests, `tests/budget.py`.
  `budget(pg, url, usable).check(usable_ms=1000, call_ms=300)` loads the page and waits until the JavaScript
  function `usable` is true. It fails if that took longer than `usable_ms` from the navigation's start, or if any
  call in the log took longer than `call_ms`, naming that call. An empty call log fails too.
  `tests/test_frontend_core.py::test_the_agents_page_is_usable_within_its_budget` uses it.

## Components

A page is composed of the shared components in `ergostat/web/static/app/components/`, one file each, imported by
absolute path. They are the "minimum before page moves" of the design, [frontend-components.md](frontend-components.md)
(section 6); the rest of its set is added by the first page that needs it. Props are data and callbacks; none fetches
but through `useApi`. Each has a browser test in `tests/test_frontend_components.py`.

```js
import { html, useApi } from "/static/app/core.js";
import { Page } from "/static/app/components/page.js";
import { Async } from "/static/app/components/async.js";
import { Table } from "/static/app/components/table.js";
```

- **`Page`** `{ title, aside, toolbar }`: the h1 with its muted aside, the filters row, then what it holds.

  ```js
  html`<${Page} title="Goals" aside=${` · goals off ${goalsOffText()}`} toolbar=${html`<input type="search" />`}>…<//>`
  ```
- **`Section`** `{ title, level = 2, aside, actions, id }`: a `section` under its heading.

  ```js
  html`<${Section} title="Daemons" level=${3} aside=${n}>${table}<//>`
  ```
- **`Note`** `{ tone, action }`: one line of words; `tone` "note" (the default), "muted", "warn" or "bad";
  `action` `{ label, href }` or `{ label, onClick }`.

  ```js
  html`<${Note} tone="warn" action=${{ label: "clear", onClick: () => setMatch("") }}>Nothing matches<//>`
  ```
- **`Facts`** `{ pairs }`: a `dl`; a pair whose value is null, undefined or "" is left out.

  ```js
  html`<${Facts} pairs=${[["kind", it.kind], ["owner", it.owner], ["in state", dur(it.age)]]} />`
  ```
- **`Table`** `{ columns, rows, rowKey, caption, cls, groups, total, rowHref, onRow, empty, hold }`: a column is
  `{ key, head, num, title, cls, cell(row) }` (its cell `row[key]` unless `cell` says). `groups` `[{ key, head, rows
  }]` draws a tbody each under its heading; `total` `{ key: content }` a last row. `rowHref(row)`: a plain click on
  the row goes there, a modified or middle click opens a new tab (util.js `rowLink`); `onRow(row)` instead calls
  back. A click on a link in a row is the link's (with `onRow`, on a button or a field too). `empty` is said in place of a table with
  no rows. `hold`: while the pointer or the focus is in it, the rows stay and "N updates waiting" is said over it.

  ```js
  const columns = [{ key: "name", head: "agent", cell: (a) => html`<${Ref} to="agent" id=${a.name} />` },
                   { key: "runs", head: "runs", num: true }];
  html`<${Table} caption="Agents, by rung" hold rowKey="name" rowHref=${(a) => agentHref(a.name)} columns=${columns}
    groups=${byRung(agents)} total=${{ name: "total", runs: total }} />`
  ```
- **`Async`** `{ of, what, empty, loading, children }`: shows a `useApi` answer. "Loading…" only before the first;
  "Still waiting for WHAT (N s)" while a call is slow, over the last data; "WHAT could not be read: why" with a
  Retry; `empty` (words, or `{ text, action }`) for an empty list or object; else `children(data)`.

  ```js
  const loops = useApi("loops", { perf: 1 }, { every: 3000 });
  html`<${Async} of=${loops} what="the goals" empty="No goals yet.">${(d) => html`<${Table} … />`}<//>`
  ```
- **`Chip`** `{ label, n, tone, on, href, onClick, onRemove, title }`: a word and its count; a link, a toggle button
  (`aria-pressed`) or words; an × with `onRemove`. **`StateChip`** `{ word, n }`: a state's word, its tone from one
  table (off bad; open and stale warn; holding and unknown quiet); no word is "–".

  ```js
  html`<${Chip} label="open" n=${4} href=${kindHref("ticket", "state=open")} /> <${StateChip} word=${goalWord(g)} />`
  ```
- **`Ref`** `{ to, id, remote, panel, title }`: a link to an item, kind, agent, goal or part. With `panel` (an opener
  such as `openAgent`) a plain click opens the side panel there; a modified click is the browser's. A `remote` item
  links to that remote's item, or is its text alone when its id cannot be opened there.

  ```js
  html`<${Ref} to="item" id=${e.item} remote=${e.remote} /> <${Ref} to="agent" id=${name} panel=${openAgent} />`
  ```
- **`Dom`** `{ node, make, deps, tag }`: the bridge to the old code. `node` shows an element made the old way;
  `make(el)` draws into the component's own box and gives back its cleanup, called when the component goes. Pass
  `deps` when `make` is written inline.

  ```js
  html`<${Dom} make=${(el) => { const u = new uPlot(opts, data, el); return () => u.destroy(); }} deps=${[data]} />`
  ```
- **`openPanel({ kind, title, body })`** (`side-panel.js`): opens the side panel with `body`, a component's drawing
  or an old element, in the one panel frame the old openers use (details.js `showDetail`: its ×, Escape, the focus
  to its heading when opened by keyboard). The body stays live (its `useApi` calls follow the window) and is
  unmounted, its calls aborted, when the panel is closed or another opened. `closePanel()` closes it as its × does.

  ```js
  openPanel({ kind: "goal", title: name, body: html`<${GoalPanel} name=${name} />` });
  ```

The hooks (`hooks.js`; `useApi` and `usePoll` are core.js's):

- **`useQueryState(key, initial, { parse, write })`** → `[value, set]`: one key of the address's query, read when
  the page is drawn (back and forward draw it again) and written in place (setQuery). By default the initial value, "" and false drop the key and true
  is written "1".

  ```js
  const [match, setMatch] = useQueryState("match", "");
  const [runs, setRuns] = useQueryState("runs", false, { parse: (v) => v === "1" });
  ```
- **`useKeys(map, { when })`**: keys while the component is drawn, `{ "Escape": fn, "mod+Enter": fn }` (mod: Ctrl or
  Cmd). Of the components that take a key, the one drawn last alone has it (a part before its page), its default
  prevented. A plain key typed in a field is the field's; Escape and mod+ keys are not. Other listeners (main.js's
  Escape closing the panel, util.js's closing menus) still hear every key.

  ```js
  useKeys({ "mod+Enter": run, Escape: () => setOpen(false) }, { when: open });
  ```
- **`useWindow()`** → `{ since, at, live, words, setSince, setAt }`: the window and the moment shown, from the store,
  and the header menu's own setters.

  ```js
  const { words } = useWindow();   // "Last hour"
  ```

The formatters (`fmt`, `dur`, `ago`, `usd`, ...) are util.js's globals, used by name (rule 4 below) until util.js
itself moves.

When a page needs something the set has not got, it builds it in its own folder first. A new generic component, or a
new prop on one, is promoted into `app/components/` once a second page uses it.

## The rules for moving a page

1. A page's gap owns only `ergostat/web/static/app/pages/<page>/`: its stub `index.js` and any new files beside
   it. It does not edit another page's files, the shared core (`app/core.js`, `app/shell.js`, `app/router.js`,
   `app/timing.js`) or the shared components (`app/components/`). When the core or a component needs a change, it
   says so in its record's "Where it stopped", for the coordinator.
2. The page behaves the same as today and adds nothing: no new explanatory text, panels or features. It drops
   nothing the page does today unless its definition says so. The heavy drawing libraries (ELK, libavoid, uPlot)
   stay, wrapped in components (a `ref` and an effect that draws into it), not rewritten.
3. Every API call goes through `useApi`, or `apiGet` for one outside the drawing, so the overlay and the budget see
   it.
4. The page still uses the old helpers it needs (`goalRow`, `RUNG_NAMES`, `dur`...). They are globals of the
   ordinary scripts, readable from a module by name. A helper that only the moved page used moves with it. One that
   other pages still use stays where it is.
5. Acceptance: the page's existing browser tests pass, each run by its id (never a whole file). A budget test with
   `tests/budget.py` also passes: usable within 1 s of navigation on the demo fixture, and no API call over 300 ms.
   A slower call is named in the record, not hidden.
6. Once the module exports `page`, the old function is no longer reached for that address. The gap deletes it in
   the same change, with the helpers only it used.

## A worked example: the Agents page's header

Today `pageAgents` (`pages.js`) starts with the page's title and the ladder: one line counting the agents on each
rung, from the most general to the most specific, with the rung's hint as each count's title:

```js
const p = page(main, "Agents");
const ladder = h("div", { class: "ladder-line" });
...
patch(ladder, ...cols.map((k, i) => h("span", { class: "step", "data-kind": k, title: RUNG_HINT[i] },
  of(i).length ? h("b", {}, String(of(i).length)) : "0", ` ${k}`)), h("span", { class: "muted" }, "most general → most specific"), ...);
```

As components, in `app/pages/agents/index.js` (the tally of exceptions at the line's end is left out here, to keep
the example small):

```js
import { html, useApi } from "/static/app/core.js";

function Ladder({ agents }) {
  const cols = [...RUNG_NAMES, "retired"];
  const of = (i) => Object.values(agents).filter((a) => a.rung === i).length;
  return html`<div class="ladder-line">
    ${cols.map((k, i) => html`<span class="step" data-kind=${k} title=${RUNG_HINT[i]} key=${k}>
      ${of(i) ? html`<b>${of(i)}</b>` : "0"} ${k}</span>`)}
    <span class="muted">most general → most specific</span>
  </div>`;
}

export function page() {
  const agents = useApi("agents", {}, { every: 3000 });
  return html`<div class="page"><h1>Agents</h1>
    ${agents.data ? html`<${Ladder} agents=${agents.data} />` : null}
  </div>`;
}
```

This example is not committed. The export alone would replace the whole old page with its header and lose the
table, the costs and the daemons. The Agents gap exports `page` once the whole page is a component. Until then the
stub stays empty and the router shows `pageAgents`. The steps:

1. Write the components beside the stub (`app/pages/agents/ladder.js`...) and export `page` from `index.js` once
   they draw all the page draws.
2. Load `/agents?timing=1` and read the overlay: `agents` and `daemons`, as before, and nothing asked twice.
3. Run the page's existing browser tests by id, and a budget test with `tests/budget.py`.
4. Delete `pageAgents` and what only it used.
