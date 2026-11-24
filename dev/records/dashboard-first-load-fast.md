# dashboard-first-load-fast: a cold dashboard draws in a few seconds

depends-on: [dashboard-v2]

Measured 2026-11-23: on a cold server under load, the first load takes about 24 s, in two requests of about 10 s each. Which query is slow is not known.

Change. Measure each query of the default dashboard on a factory-size record (`factory_state`), find what dominates, and serve it from the item index or a cached roll-up. Panels above the fold are asked for first.

Definition of done.
1. A test on the factory-size record holds the default dashboard's first answer under a stated budget on a cold server.
2. Each query's time is recorded in the test's output.
3. Answers are identical to before.

Files: ergostat/query/, ergostat/spec/itemindex.py, tests.

## Where it stopped

Round 1 (2026-11-23). Nothing built: this gap waits for `dashboard-v2`, which is not on main.

- What is missing on main (the clone's `main`, e43046dc): there is no Dashboard page and no dashboard query to
  measure. `ergostat/query/` (named in Files) does not exist. No `/dashboard` route or `/api/dashboard` handler is in
  `ergostat/web/` (a search for "dashboard" there finds nothing). No `dev/records/dashboard-v2.md` or
  `dashboard-page-v1.md` exists, and no commit names either. The only dashboard work on main is the proposal
  (docs/proposals/dashboard.md, prose; its section 8 gives the default's panels) and the chart forms
  (static/plots.js, not used by any page).
- So none of the three done items can be met: there is no "default dashboard's first answer" to hold under a
  budget, no per-query times to record, and no "before" answer to compare with.
- Decision taken alone (most reversible): not to put another page (say `/` with its /api/status and /api/graph) in
  the dashboard's place. That would mean guessing what the 24 s measurement was of, and building outside the gap.
  When `dashboard-v2` lands on main, this gap starts again from its definition as written, with no code from this
  round to undo.
- Left: everything in the definition. That means measuring each query of the default dashboard on `factory_state`,
  serving the dominant one from the item index or a cached roll-up, asking for above-the-fold panels first, and the
  three tests.

Not run: no test and no ruff, because no code changed (this section is the only change). main has not moved since
the branch was made, so there was nothing to merge.

## Where it stopped

Parked by the factory (review/dashboard-first-load-fast-1, 2026-11-23 03:34).

Done: only the definition of done and a 'Where it stopped' note; no code, no tests. Left: everything. Measure each query of the default dashboard on factory_state, serve the dominant one from the item index or a cached roll-up, ask for above-the-fold panels first, and write the three acceptance tests (cold first answer under a stated budget, per-query times in the output, answers identical to before). Why stop: there is no dashboard on main to measure. ergostat/query/ and the dashboard route and handler arrive with gap/dashboard-v2 (origin/factory/dashboard-v2, 762ad7eb), which is not an ancestor of origin/main.

## Where it stopped

Continued, round 1 (2026-11-24). The Dashboard is on main now (dashboard.js, panels.js, ergostat/query/), so the
gap was built from its definition as written. Built; the three done items hold, with the limits below.

**What was measured** (`factory_state`, `ergostat web` started cold on it, the page in Chromium at 1440x900). The
default dashboard is made in the page: `/api/query/fields`, `/api/items?n=1` (its kinds' rows),
`/api/items-graph?kinds=gap,review,lesson` (their queues), then its panels' queries in one `/api/query` of 29. Beside
that batch the header asks `/api/status?since=1d` (the page's window is a day). Before: the batch took 10.4 s and hit
the engine's 10 s request limit, so its last queries came back busy and were asked again (1.7 s more). The status took
16.7 s, and the panels drew about 14.5 s after the page's first request. Each query alone took 0.00-0.08 s, and all
29 at once 0.3 s. So the dominant cost was **not a query**. Both `/api/items` and `/api/items-graph` start the
completion estimates' simulation (`eta_api`) on their first asking, in a thread of the server. That thread, CPU-bound
Python, held the GIL and, in turns, the item index's lock while the panels and the status were answered. This was
reproduced in-process: with the `eta` thread running, the batch takes 7.4 s and the status 16.4 s; without it, 0.65 s
and 2.4 s. The dashboard reads neither the estimates nor the Graph; it wanted the kinds' rows and their queues.

**Changed** (31 net lines outside tests and docs; budget 600):
- `ergostat/query/fields.py`: each kind under `moves` has its `queue`, `finished.finish_of`'s, the same list the
  Graph gives (`precedence.Kinds`), from the model and the item index.
- `ergostat/web/static/dashboard.js`: the default reads the queues there and no longer asks for `/api/items-graph`.
  It takes the same kinds as before: the three leading ones, and those their relations name. It asks
  `/api/items?n=1&eta=0` for its kinds' rows. It asks first for the panels whose cell begins above the fold (`dashFirst`),
  draws them, then asks for the rest at the first answer's `until`, so all are of one moment.
- `ergostat/web/server.py`: `GET /api/items?eta=0` leaves out the estimates (and so does not start their simulation);
  without it, nothing changed.
- SPEC §4e says all three.

**After** (the acceptance test's output on this container): the 13 above the fold answered in 0.72 s, 1.92 s after
the page's first request; the other 16 in 0.08 s; the day's status 2.50 s.

**The acceptance tests** (`tests/test_dashboard_first_load.py`):
- **1 and 2.** `test_a_cold_servers_first_dashboard_answer_is_within_budget` (slow, serial). It replays the page's
  first load over HTTP against `ergostat web` started cold, as the page sends it: the hour's status, the fields, the
  listing, then the first batch beside the day's status, then the rest. It holds the first batch to 3 s from being
  asked, and to 6 s from the page's first request. It holds the day's status to 6 s, and every query answered with no
  error. It writes each request's time, and each query's time alone afterwards, to the output (`capsys.disabled`).
- **3.** The answers:
  - The split's answers equal one request of all 29 at that moment (same test).
  - `test_the_queues_the_fields_give_are_the_graphs`: every kind's queue, fields against `precedence.Kinds`.
  - `test_the_listing_with_eta_0_is_the_listing_without_its_estimates`: same answer, and no estimate started.
  - `test_the_page_sends_what_the_replay_sends` (Playwright): no Graph asked, the listing asked with `eta=0`, the two
    batches exactly the replay's, and the default drawn equal to the one built from `/api/items-graph`'s queues as
    before.
- `tests/test_dashboard_page.py`: its fake fields carry the queues its fake Graph gave. Its whole-window stat test
  reads every request's queries (`__every`), since the stat's query is now in the first request.

Breaks seen to fail (lesson 9):
- The listing ignoring `eta=0`: the budget test, first batch 7.27 s.
- All panels in one request: the page test, 16 extra queries in the first.
- The Graph asked again: the page test.
- No queues read from the fields: the page test (the default's queries differ).
- The fields' queue cut to its first state: the queues test.

Tried and not kept: the fold with a transcript's events re-folds the status's tables (projections.py), most of its
first catch-up. Making it read the plain fold's took that from 12 s to 0.7 s in-process. On the shipped server it moved
neither the first load (the test passed without it, the day's status 2.24 s) nor the server's start (10.8 s against
11.7 s), so it was taken out, to build only what the measurement asks.

Decisions taken alone (the most reversible each time):
- "Cold server" means `ergostat web` just started with nothing kept. Its own start (about 11 s here, the record's
  plain item index folded) is said in the output, not budgeted: it comes before any page.
- "Above the fold" means a panel whose cell's top is inside the window's height. With none placed, all are asked
  at once.
- The replay pins the page's queries on this record (`FIRST`, `REST`). The Playwright test holds the page to them,
  but no gate runs it: the unit suite has no Playwright, and the four browser files are named. It was run here.
- A kind a relation names, none of whose items the Graph reached, now gets its declared queue; before, it got its
  first state only. On this record every such kind is reached, and the default is identical (the page test).

Not run here: the unit suite and the four browser files (the factory's and the queue's). Run here, one file at a
time:
- `tests/test_dashboard_first_load.py`: 4 passed, with Playwright.
- `tests/test_dashboard_page.py`: 36 passed.
- `tests/test_dashboard_layout.py`: 26 passed, with test_dashboard_page in one run.
- `tests/test_data_source_panels.py`, `tests/test_promql_editor.py`, `tests/test_dashboards_doc.py`: 44 passed.
- `tests/test_query_engine.py`, `tests/test_query_fixes.py`: 71 passed.
- `tests/test_index_projections.py`, `tests/test_item_index.py`: passed, while the reverted change was in place; the
  files are unchanged since.

`uv run ruff check ergostat tests scripts` is clean. main has not moved since the branch's last merge of it
(278f54a4).

Left for others: each cold server still starts a `python -m ergostat.numbers.extremes_cache` process in its own
session. It outlives the server by up to a minute (it stops at its own 65 s alarm), here and in the tests.

## Entry

section: Done recently

- **A cold dashboard draws in a few seconds** (done, on `dashboard-first-load-fast`; SPEC §4e): on the factory-size
  record, a cold server's first dashboard answer took 10-14 s, held back by the completion estimates' simulation that
  the default's `/api/items` and `/api/items-graph` started. The default now reads each kind's queue from
  `/api/query/fields` and asks the listing with `eta=0`, and the panels above the fold are asked first: 0.7 s for them,
  under 2 s from the page's first request (`tests/test_dashboard_first_load.py`).
