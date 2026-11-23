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
