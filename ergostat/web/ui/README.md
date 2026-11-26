# ergostat's page, in React

ergostat's page. It is built into `../static/app/` and served by ergostat's own server at `/` and at each page's path
(`UI_PAGES` in `../server.py`, one per route in `src/App.tsx`). Python needs nothing at runtime: the built files are
committed. The old vanilla-JS page it was ported from is gone (2026-11-25), with its Model, Check and Guide pages, the
header's project list and `ergostat snapshot`.

    npm install
    npm run dev        # http://localhost:5173/goals, the API proxied to ERGOSTAT_URL (default 127.0.0.1:8781)
    npm run check      # tsc
    npm run build      # tsc, then vite into ../static/app

## Layout

    src/
      main.tsx, App.tsx      the router: one route per page, each page loaded lazily
      styles/                the page's styles (style.css, panels.css, plots.css, panel-editor.css, dashboard.css)
      lib/                   pure functions: api.ts (apiGet, apiPost, apiSend), format.ts (fmt, dur, ago, stamp,
                             rateText, op, holdText, windowNote, plural...), rung.ts, hrefs.ts (itemHref, kindHref,
                             agentHref, diagramHref), goals.ts (a goal in words), query.ts (what a panel asks /api/query)
      state/                 app-wide context: time.tsx (window and moment, in the address), status.tsx (/api/status
                             every 5 s: useStatus())
      hooks/                 usePoll (a refresh that never overlaps, pauses while hidden), useApi (an answer, with
                             the window, polled when asked: { data, error, loading, refresh })
      components/            the components any page is composed of (index.ts):
        ui.tsx, Table, Menu,   Page, Section, Table/DataTable/Fields, Dl, Menu, Tabs, Detail (the side panel:
        Detail, Markdown       useDetail().open(key, node)), Markdown, Code, StatusWord, Rung, Button, Select...
        links.tsx            AgentLink, ItemLink (here or on a remote), KindLink
        events.tsx           EventsTable (compact, fold), EventDetail, useShowEvent(), changeOf
        items.tsx            KindBar, ItemsTable, FieldValue
        goals.tsx            GoalCells: one goal's row in the columns asked for
        charts/              Chart (uPlot), Plot, PanelView (a query's panel from its answer), QueryPanel and
                             usePanelResults (a panel that asks for its own answer), Spark, FlowChart
        diagram/             imported from "components/diagram" (it brings ELK): Diagram (asks for its own graph:
                             <Diagram view="blocks" system="x" />), DiagramCanvas (draws a graph a page has), the
                             three drawings, useDiagramLayout, usePanZoom, a part's panels (usePartPanels)
      pages/<page>/          one folder per page; index.tsx is the page, composed of components/.

## Rules

- Compose pages from `components/`. Anything another page could show (a table, a chart, a link, a drawing) is a
  component there, taking its data as props or asking for it itself; a page's folder keeps only what is that page's
  alone: its layout, its toolbar, what it keeps in the address.
- Data comes from `useApi(path, params, { every })`, never from fetch in a component. Writes use `apiPost`/`apiSend`
  from `lib/api.ts`, then `refresh()`.
- No global mutable state. The window and moment are `useTime()`; the status is `useStatus()`.
- Use the class names `styles/style.css` and friends draw; add new styles to the page's own `.css` file.
- Geometry and layout code (ELK, libavoid, routing, placing) is plain TypeScript in `lib/` folders, with no React and
  no DOM: React renders what it computes.
- The words are ergostat's (NOTES.md): work, item, sensor, controller, valve, agent, rung... never task or worker.

## Where the port stands (2026-11-25)

Every page has a route and draws from the real API; none is at parity with the old page yet. Its smoke tests are
`tests/test_react_pages.py` (each page renders with no page errors). Not ported:

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
- **Record:** its `window=1` scope shares the `window` parameter with the header's window, as on the old page.

Still to move into `components/`: a segmented toggle, a dialog (dashboard/Editor), a goal panel (goals/GoalDetail,
diagram/Side).
