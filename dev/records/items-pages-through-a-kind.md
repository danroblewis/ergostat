# items-pages-through-a-kind: Items: an open kind pages through all its filtered items, sorted on the server, and the search reaches every item

depends-on: [items-one-section-per-kind-closed]

Problem: 'All N' (ergostat/web/static/pages.js:757-758) only sets kind=, which asks 300 rows; past that the page says 'N older items not loaded' (pages.js:799). The factory has kinds of 366 and 428, the roadmap 1,180 tickets. The server already pages (n, offset; LISTED=500, ergostat/spec/items.py:30; in_states_page, spec/items.py:339, 560) but the page never asks for page 2. The search q is applied after the server cut its 500 newest (server.py:281-286), so an older item is never found and match counts are wrong. A column sort (pages.js:224-229) orders only loaded rows. Owner: 'no real pagination, so the problem returns right after clicking it'.
Change: an open kind shows 25 rows with a pager in its bar and the table's foot: '1-25 of 77 unfinished · Prev · Next' with a page size of 25, 100 or 300; the page is in the address (page=gap:3); the request is that kind, its states filter, offset and n; the poll refreshes the page shown. With a search, the kind's rows come from the index's word search (spec/items.py _paged / the existing search path) over every item of the kind, finished ones included (the rule of items-list-hides-finished-by-default: a search never hides a match), so count and pages are of all matches, with the finished ones counted apart ('3 matches, 1 finished') beside the box (filed Q32). A column sort is sent to the server (sort=gap:-ai_cost_usd), which sorts the whole filtered set (up to 5,000 items read without moves; past that the newest 5,000, said in the caption), then pages. A page past the end falls back to the last page. 'All N' and the 'older items not loaded' note are removed.
Definition of done:
1. On a fixture of 1,200 items of one kind every item is reached by Next; the last page's last row is the oldest.
2. page=gap:24 in the address opens that page; a refresh on page 3 stays on page 3.
3. Searching an id that is the 1,000th newest finds it and the count reads 1; searching a finished item's id finds it with the finished filter at its default.
4. Sorting by a numeric column puts the set's global maximum (checked through the API) on page 1; the page and sort survive a reload.
5. No element with text matching /^All \d+/ or 'not loaded' exists.
6. SPEC §5a documents offset, n and sort for /api/items with one kind.
Files: ergostat/web/static/pages.js, kinds.js, style.css, ergostat/web/server.py (items handler: search for a kind via the index, offset, sort), ergostat/spec/items.py (sorted page over in_states_page), docs/SPEC.md, tests/test_items_page.py, tests/test_item_search.py or tests/test_item_index.py.
Acceptance tests: unit tests for offset + search totals and the sort cut at 6,000 items; browser tests for pager, address and sort on the roadmap fixture.
Budget: 200 net lines.

Milestone: items-page-readable. Owner items: 14. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1: 116 net lines outside tests and docs (within the 200 budget).

- `items.kind_page` (`ergostat/spec/items.py`) reads one kind's rows from the item index: ids, states and times only
  (an id holding `q`, or text holding each of its words, as two index queries merged), then folds only the page shown
  (or, with `sort`, up to `SORTED_MOST` = 5,000 newest, without moves, sorted by the field and paged: `cut` says so).
  Items changed after a travelled-to moment come from `_late`, and with no index (or most items late) it reads
  `project`, as the other index readers do. An offset past the end is the last page's. `total` and `finished` (of the
  kind's finished states) count every match.
- `/api/items?kind=K` (a kind in the model, not a `where`/`moved`/process-map set) answers from it with `state`,
  `offset`, `n`, `q` and `sort`, plus the listing's kinds, systems and counts; the cross-kind list, sets, remotes and
  snapshots are as before.
- The kind's page (`pages.js`): a pager in the kind's bar and under its table (*1-25 of 1200 · Prev · Next*, 25, 100 or
  300 a page), `page=KIND:N`, `size=` and `sort=KIND:-FIELD` in the address, a new search, sort, state or size goes
  to page 1, the poll asks for the page shown, and *N matches, M finished* beside the search box. 'All N' and the
  'older items not loaded' note are gone. SPEC §5a: *A kind's page*, and `offset`/`n`, `sort`, `q` rows in the filters table.

Decisions taken with nobody to ask (the most reversible each time):
- items-list-hides-finished-by-default is not built (not on main), so there is no finished filter: a kind's page lists
  all its items (or the one state chosen), and the pager says *of 1200* (*of 77 review* with a state), not *unfinished*.
  Done item 3's "finished filter at its default" therefore holds trivially; the test checks a finished item is found
  and counted as finished. When that gap lands, its filter is one more `state`-like argument to `kind_page`.
- The page's search on a kind matches the id as a substring as well as the index's words in the fields (the word search
  alone never reads ids, and done item 3 searches an id). It no longer keeps every item when the search names the kind
  (on the kind's own page that would make any search of its name match everything).
- Sort order: numbers as numbers, then text, missing or non-finite values last, newest first among equals.
- A plain `sort=FIELD` (old links) is still read on a kind's page; it is written back as `sort=KIND:FIELD`.

Found on the way (lesson 5, fixed here since the new pager hit both): the column header's sort handler and the pager's
buttons read the render's values; a click before the next render, or a poll's older answer landing after a click, put
the page back. Both read the current value now, and the past-the-end fallback compares the answer with the page it
asked for. Each was seen failing the browser tests before the fix.

Tests: `tests/test_item_search.py` (three new: paging all 1,200, the 1,000th newest found and counted once, a finished
one found, match and finished totals; the sort over the whole set and its cut at 6,000 items; the API's offset, past
the end, `q` and `sort`); `tests/test_items_page.py` (two new on the roadmap example with 1,200 tickets: Next through
every item, `page=ticket:24`, a reload on page 3, past the end, no 'All N' or 'not loaded'; the search and the server
sort against the API's maximum, surviving a reload). `test_items_list_sorts_by_a_column` now waits for
`sort=hypothesis:title`. Seen failing: the unit tests with the id search removed, with the sort removed and with the
5,000 cut removed; the browser sort test with the page's sort left out of the request.

Run here: `tests/test_item_search.py` (11 passed); `tests/test_item_sets.py`, `test_item_systems.py`,
`test_item_index.py` (74 passed); `tests/test_items_page.py` whole (56 passed, 2 failed, below); of
`tests/test_diagram_rendering.py` the links, charts-and-snapshot, process line panel, loading and snapshot process
line tests (6 passed); ruff clean. Main merged (already up to date). Not run here: the unit suite and the four browser
files as wholes, and `tests/test_page_polling.py` (a long background run was refused in this session).

Unrelated failures in `tests/test_items_page.py`:
- `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`: the project switcher never lists the other
  project in this container, as items-one-section-per-kind-closed recorded.
- `test_actions_say_per_class_asked_approved_denied_and_whether_held`: it opens bare `/items`, which `util.js` routes to
  the overview (`kinds.js`, untouched here), so the per-class line it waits for is never drawn. Neither file is changed by
  this branch. It could not be checked on clean main here: `git worktree add -q /tmp/main-wt main` was refused.
