# items-one-section-per-kind-closed: /items is an overview of the item kinds; each kind opens on its own page

Rewritten 2026-11-22 from the owner's direction: "an initial page that shows types of items and metrics per type (like the graphs), and click through to get to a specific item type. We rarely want to use the whole page, so we can speed it up by splitting it ... We want to fit the majority of our item types displayed above the fold."

Problem: /items draws every kind's charts and lists at once: about 8,000 elements and 26 to 28 API requests per load on the factory's record.

Change:
- `/items` becomes the overview. Under each system heading, one compact card per kind in a dense grid: the kind's name (a link to `/items/<kind>`), how many are unfinished and in all, a small state chart over time, and the rate in and out.
- The overview draws no item rows and offers no List, Graph or Timeline switch. Those belong to the kind's page (`the-kind-page`).
- Each chart's legend sits to the right of the chart, not under it.
- A chart shows **state groups** by default (waiting, working, done, stopped, derived from the kind's states and its finished states) with one page-wide toggle to show every state. The choice is kept in the address.
- The whole overview comes from **one** request (`/api/items-overview?since=...`), which reads the item index and the stored counts and never replays the event log. Kinds with no items in the window are folded into one line at the end.

Definition of done:
1. On a generated record of the factory's shape (about 25 kinds, 700 gaps, 2,500 sessions), `/items` makes exactly one data request for its cards besides the page's shared header calls, and has no table row in the DOM.
2. `/api/items-overview` answers in under 200 ms on that record, measured in a test with a generous bound so it is not flaky, and performs no event-log scan (a test counts the segment queries).
3. At 1440x900 at least 16 kind cards are entirely above the fold.
4. The legend is to the right of each chart at 1440 px and the layout stacks with no horizontal scroll at 390 px.
5. The state-group toggle changes every chart with no further request, and survives a reload through the address.
6. A card's title goes to `/items/<kind>`; `/items?kind=K` redirects there. Until `the-kind-page` lands, `/items/<kind>` shows the existing list, graph and timeline for that one kind.
7. SPEC §5a and the Guide's Items text describe the overview.

Files: `ergostat/web/static/kinds.js` (new), `pages.js`, `charts.js`, `style.css`, `ergostat/web/server.py` or a small `items_overview.py`.
Tests: unit tests for the endpoint and the state groups, and structure-only browser tests; the browser suite is not run on each merge, so items 1, 2 and 5's logic must also be covered without it.

Milestone: items-page-readable.

## Where it stopped

Built, round 1 (about 220 net lines outside tests and docs, within the 600 budget).

- `GET /api/items-overview` (`ergostat/web/items_overview.py`, one new index query `Index.in_window`) answers before
  any snapshot is made, from the item index only. `tests/test_items_overview.py` covers the state groups, the summing,
  an item changed after the moment, no snapshot taken, and on a generated factory-shaped record
  (`tests/factory_shape.py`: 25 kinds, 700 gaps, 2,500 sessions) the best of three answers under 200 ms with no call
  to the segment store's `_rows`, `_scan`, `counted`, `items` or `times` (seen failing when a `query` was added).
- `/items` is the overview (`kinds.js`); `/items/KIND` is the old list, graph and timeline for that kind alone;
  `/items?kind=K` goes there. Browser acceptance tests are in `tests/test_items_page.py` (the three `factory_site` tests).
  The toggle test was seen to fail with the switch broken.

Decisions taken with nobody to ask (the most reversible option each time):
- `/items` with any other question (`q=`, `view=`, a set without a kind) still draws every kind's list as before, so
  older links and the cross-kind search keep working; that list writes `?view=list` into its address when nothing
  else is asked, since bare `/items` is now the overview. The overview's search box opens that list (`/items?q=...`).
  The fold of a system (and its `hide=`) remains on that list only.
- A kind is "quiet" (folded into the last line) when none of its items had an event in the window and none is
  unfinished. Rate in: items that arrived in the window, per hour; out: items first finished in it, per hour.
- A remote's section (SPEC §4c) is still drawn under the overview with its newest items (rows); the factory has no
  remote, so done item 1's "no table row" holds there, not for a project with remotes.
- The in-app Guide has no Items text to change; `docs/AGENT-GUIDE.md`'s Items sentence and SPEC §5a (*The overview*)
  describe it.
- Existing browser tests that relied on bare `/items` being the full list now open `/items?view=list` or `/items/ticket`.

Run here: `tests/test_items_overview.py` (6 passed); `tests/test_items_page.py` whole (35 passed, 1 failed, below);
`tests/test_page_polling.py` and, of `tests/test_diagram_rendering.py`, the links, charts-and-snapshot, loading and
waiting-for-you tests (all passed); `tests/test_snapshot_sets.py`, `test_series.py`, `test_item_index.py` (65 passed);
ruff clean. Not run here: the unit suite and the four browser files as wholes, and
`test_the_readers_pages_name_no_command_yaml_line_or_spec_section` (stopped at the 10-minute limit with the others).

Unrelated failure: `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`
times out waiting for the header's project switcher to list the other running project (line 1455); it fails the same
way when the test opens `/loops` instead of `/items`, so it is not this change (the project lister in this container).
