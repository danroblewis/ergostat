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

## Where it stopped

Round 1 (2026-11-24). Built: all six items, and the done line holds as below. Size: 286 net lines of code outside
tests, docs and dev (341 added, 55 removed, from the definition's commit; the coordinator's vendored module is not
counted).

**What was built.**
- `app/core.js`: the re-export; `createStore`, the shared `store` (window, at, project, status, route) and `useStore`;
  `apiUrl`, `apiGet`, and `useApi(path, params, { every })` → `{ data, error, loading, ms, reload }` (aborts on
  unmount or a new key, polls at least 500 ms apart, never while hidden; an unchanged answer draws nothing).
- `app/shell.js`: the header as components (Status: the two counts with their titles, from `util.js headerCounts`;
  Nav: the page marked from the store), then the old start (`main.js startPage`). `app/router.js`: `pageOf`,
  `mount`, `leave`, each page module imported once at the start. `route()` (util.js) mounts the module when it
  exports `page`, else the old function, and unmounts a new page when leaving it.
- The nine stubs under `app/pages/`, each a comment and no export.
- `app/timing.js`: the overlay (Shift+T, `?timing=1`), reading one call log, `util.js timed` →
  `window.ERGOSTAT_CALLS` (the last 500), which `api`, `apiPost`, `apiSend` and `useApi` all write.
- `tests/budget.py`, used by `test_the_agents_page_is_usable_within_its_budget`.
- `docs/frontend.md`, with the Agents header as the worked example (in the doc only; see below).

**Choices made alone (the most reversible, said here).**
- `index.html` keeps its static header: the served HTML is read by
  `test_graph_cli_web.py::test_every_page_header_links_to_the_diagrams_waiting_for_you_heading`, and a snapshot (a
  file, which loads no ES module) still starts on it. The shell clears it and draws its own over it before the old
  start runs. `main.js`'s load-time header code moved into `startPage()`, which the shell calls, or main.js itself
  when `HASHED` (snapshot or file). `snapshot.py` leaves the module tag out of a snapshot.
- The project list and the window's menu stay old code, filled into the shell's elements (they are not redrawn by
  Preact). The window menu is main.js's whole window logic; moving it is a later gap's.
- The store is written by the old code for now (`route()` and `refreshHeader()` call `sync()`), so there is still
  one status poll (`test_page_polling.py::test_leaving_a_page_stops_its_polling` counts it).
- `/check`, `/guide` and `/agent/NAME` have no stub (none was asked for): always their old function.
  `panel-editor` has no address, so the router never mounts it; the Dashboard uses what it will export.
- The fetches `dashboard.js`, `panels.js` and `export.js` make themselves are not in the call log; they are those
  pages' files, so their gaps route them through `useApi`.
- `?timing=1` is taken out of the route (util.js `currentRoute`), so `/items?timing=1` is still the overview.
- The worked example is not committed as the agents module: exporting `page` with only the header would replace the
  whole old page and drop its table, costs and daemons.

**Measured** (the budget test on image-squeeze seeded as test_page_polling seeds it; a warm second load; this
container, quiet): the Agents page was usable after 263 ms; its calls were status 43 ms, agents 5 ms, daemons 3 ms,
projects 3 ms. Nothing over 300 ms.

**Tests run** (each by id, under the watchdog; all passed):
- New, `tests/test_frontend_core.py` (all five): the shell and old pages; a module exporting `page` mounted, timed,
  its held call aborted when left, mounted again on back; useApi's polling floor, hidden tab and no redraw; the
  overlay; the budget. Each was seen to fail when its code was broken: `leave()` made a no-op (no `aborted` call);
  the overlay's field check removed (Shift+T in the Record's search opened it); the 500 ms floor lowered (19 polls
  in 2 s); the hidden check removed (asked while hidden); a 0 ms budget (the helper's message names the time).
- Existing browser tests: test_diagram_rendering.py::{test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back,
  test_what_waits_for_you_is_one_step_from_every_page, test_a_changed_count_of_what_waits_is_announced,
  test_needs_attention_is_three_headed_groups_in_a_fixed_order, test_the_window_in_the_header_never_claims_more_than_the_record,
  test_the_address_holds_what_is_chosen_and_the_window, test_the_goals_page_says_each_goals_word_as_the_server_does_live_and_from_a_snapshot,
  test_a_snapshot_page_still_routes_its_lines, test_the_guide_draws_every_frame_live_and_in_a_snapshot,
  test_the_model_page_says_what_is_available_and_opens_each_tools_panel, test_check_and_the_model_page_say_each_thing_once_in_a_table,
  test_every_view_loads_with_no_console_error_or_warning, test_the_split_opens_from_each_edge_resizes_halves_and_closes_at_the_edge};
  test_page_refresh.py::test_the_header_menu_lists_running_projects_then_counts_the_stopped;
  test_page_polling.py::{test_leaving_a_page_stops_its_polling, test_the_goals_page_and_its_old_address,
  test_leaving_a_page_cancels_its_fetches_in_flight, test_a_hidden_tab_asks_for_nothing};
  test_keyboard_story.py::test_story_h5_the_off_goal_found_and_read_by_keyboard_alone;
  test_dashboard_page.py::{test_the_route_and_the_nav_entry_after_diagram, test_the_header_window_is_used_and_kept,
  test_a_diagram_panels_poll_is_answered_with_its_values_alone, test_the_dashboard_keeps_its_own_window_when_the_page_is_routed_again,
  test_a_snapshot_says_the_dashboard_needs_the_live_server}; test_golden_pages.py::test_the_default_dashboards_panels_match_their_reference;
  test_agent_page.py::test_a_row_on_agents_goes_to_its_page_and_the_panel_links_it;
  test_items_page.py::{test_the_header_status_leaves_the_navigation_its_room, test_kinds_are_grouped_by_system_and_charts_sit_three_across,
  test_the_record_folds_runs_of_identical_events, test_an_item_page_shows_its_path}.
- Unit files: test_graph_cli_web.py, test_codebox.py, test_style_tokens.py, test_architecture.py, test_footprint.py,
  test_page_names_source.py, test_ui_front.py, test_web_access.py, test_snapshot_sets.py. `ruff check` is clean.
- Not run here: the whole unit suite, the four browser files and demo_check (no example touched); the merge queue
  runs them. Main had not moved since the branch (`git merge main`: already up to date).

**Left for the page gaps**: each fills its stub (docs/frontend.md, "The rules for moving a page").

## Entry

section: Interface

- **Frontend refactor foundation** (done, on `preact-foundation`; docs/frontend.md): the page is moving to Preact
  with htm (vendored, no build step). The header (the two counts, the navigation) is a Preact shell. The router
  mounts `app/pages/<page>/index.js` when it exports `page`, else the page's old function, so each page moves on its
  own. `app/core.js` has `useApi` (timed, aborted on leaving, polled) and a shared store. Shift+T or `?timing=1`
  lists every API call, slowest first. `tests/budget.py` holds a page to its time to usable and its slowest call.
  *Left*: every page's own move (its stub), `/check`, `/guide` and `/agent/NAME`.
