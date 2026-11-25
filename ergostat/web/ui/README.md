# ergostat's page, in React

The React port of the page in `../static/*.js`. It is built into `../static/app/` and served by ergostat's own server
at `/ui/...` (the old page stays at `/` until this one has every page). Python needs nothing at runtime: the built
files are committed.

    npm install
    npm run dev        # http://localhost:5173/ui/goals, the API proxied to ERGOSTAT_URL (default 127.0.0.1:8781)
    npm run check      # tsc
    npm run build      # tsc, then vite into ../static/app

## Layout

    src/
      main.tsx, App.tsx      the router: one route per page, each page loaded lazily
      lib/                   pure functions: api.ts (apiGet, apiPost, apiSend), format.ts (fmt, dur, ago, stamp,
                             rateText, op, holdText...), rung.ts
      state/                 app-wide context: time.tsx (window and moment, in the address), status.tsx (/api/status
                             every 5 s: useStatus())
      hooks/                 usePoll (a refresh that never overlaps, pauses while hidden), useApi (an answer, with
                             the window, polled when asked: { data, error, loading, refresh })
      components/            the core components (index.ts): Page, Section, Table/DataTable/Fields, Menu, Tabs,
                             Detail (the side panel: useDetail().open(key, node)), Markdown, Code, Chart (uPlot),
                             StatusWord, Rung, Button, Select, Check, Filters, Fold, Async, Empty, Note, ErrorNote...
      pages/<page>/          one folder per page; index.tsx is the page. A page's own parts stay in its folder.

## Rules

- Compose pages from `components/`; a part used by one page lives in that page's folder. A part two pages need moves
  to `components/`.
- Data comes from `useApi(path, params, { every })`, never from fetch in a component. Writes use `apiPost`/`apiSend`
  from `lib/api.ts`, then `refresh()`.
- No global mutable state. The window and moment are `useTime()`; the status is `useStatus()`.
- Keep the old page's class names so `style.css` and friends draw it; add new styles to the page's own `.css` file.
- Geometry and layout code (ELK, libavoid, routing, placing) is plain TypeScript in `lib/` folders, with no React and
  no DOM: React renders what it computes.
- The words are ergostat's (NOTES.md): work, item, sensor, controller, valve, agent, rung... never task or worker.

## Where the port stands (2026-11-25)

Every page has a route and draws from the real API; none is at parity with the old page yet. Not ported:

- **Diagram:** the old layout presets (anchors, satellites, rows, upright pipes), libavoid routing, pins and dragging,
  loop markers, flows-only, correspondence colouring, dominance charts; Blocks' frames, fractions and MathML; inbox
  answer buttons, keys, the split pane, PNG/Markdown export, equations, `have=` (every poll fetches the whole graph).
- **Dashboard:** plot kinds beyond line/area/stacked/step/bar/stat/table; the 12-column grid with drag and resize;
  rows, repeats, variables, `?draft=`, `?name=` dashboards, Keep; the code box (highlighting, keys), SQL suggestions,
  display options. The built-in PromQL source `ergostat` is detected by a probe query, because the server's listing
  (`datasources.listed()`) drops it on SQLite without saying why.
- **Goals / Agents:** the goal panel's charts (scope, forecast, step response, Bode, fit) and MathML; the agent page's
  run and cost charts, resources fold and version spans.
- **Items:** the Graph and Timeline views, item sets, set chips (`where=`, `moved=`...), built-in kinds' views
  (claims, decisions, messages, gated actions, reports), notes, Impact, leases, remote items.
- **Model:** "What's available", effect simulations, redesign. **Guide:** each frame's small diagram.
- **Record:** its `window=1` scope shares the `window` parameter with the header's window, as on the old page.

Parts written in more than one page, to move into `components/`: an events table (record/, items/), a segmented
toggle, a sparkline, a dialog (dashboard/Editor), a goal panel (goals/GoalDetail, diagram/Side), a link to a part
on the diagram (check/), a chart that fills its parent's height (dashboard/Plot).
