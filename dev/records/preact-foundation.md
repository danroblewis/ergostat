# preact-foundation: Frontend refactor foundation: Preact and htm, the router that mounts new or old pages, the API hook with timing

The vendored library is already committed on this branch (ergostat/web/static/vendor/preact/), by the coordinator.

Build the shared core in `ergostat/web/static/app/`:
1. `core.js`: re-export of the vendored module; `useApi(path, params)` (fetch, abort on unmount, loading and error state, latency recorded); a small store for shared state (the window, the project) with hooks.
2. The app shell as a Preact component: the header and navigation (as the header looks after header-status-out-of-the-nav: two counts with tooltips, nothing else), and the router. The router mounts `app/pages/<page>/index.js` when it exports a page, and otherwise calls today's page function from pages.js and friends, so every page keeps working.
3. One stub per page, `app/pages/<page>/index.js`, exporting nothing yet: dashboard, panel-editor, diagram, items, item, goals, agents, record, model. Page gaps fill only their stub's folder.
4. A request timing overlay, off by default, opened by a key (Shift+T) or `?timing=1`: each API call with its path and milliseconds, slowest first.
5. A budget test helper for browser tests: time to usable and the slowest API call.
6. docs/frontend.md: the rules above and how to move a page, with one worked example (the agents page header, small).

Done: every existing page still works through the router (its existing browser tests pass, by id); the overlay shows calls; the helper is used by one test; docs/frontend.md exists.

Project rules (the owner, 2026-11-24: "prioritized right now ... as quickly as possible"; the coordinator leads, the factory builds):
- Preact with htm, no build step, as ES modules: `import { html, render, useState, useEffect, ... } from "/static/vendor/preact/htm-preact-standalone.module.js"`. No other library, no bundler, no network (it is vendored).
- Old and new coexist: the foundation's router mounts a page's new module when it exists and its old page function otherwise, so each page moves on its own and the site always works.
- Each page gap owns only its own new files under `ergostat/web/static/app/pages/<page>/` and its one stub; it does not edit another page's files or the shared core (ask the coordinator through "Where it stopped" if the core needs a change). This keeps parallel gaps from conflicting.
- Same behaviour as today, nothing added: no new explanatory text, panels or features; drop nothing the page does today unless the definition says so. The heavy drawing libraries (ELK, libavoid, uPlot) stay and are wrapped in components, not rewritten.
- Every API call goes through the core's `useApi`, which records its latency, so the timing overlay shows it.
- Acceptance: the page's existing browser tests pass (run by test id, never a whole file), plus a budget test: the page is usable within 1 s of navigation on the demo fixture, and no API call it makes takes over 300 ms on the fixture (a slower one is named in the record, not hidden).
- Do not measure or change the live instance in the session.
