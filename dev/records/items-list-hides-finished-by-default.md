# items-list-hides-finished-by-default: Items lists leave finished items out by default from one page-wide choice, never hide a searched or linked item, and a filter click answers at once

depends-on: [items-kinds-say-which-states-finish]

Problem: /items lists every state by default (ergostat/web/static/pages.js:642-644 asks per_kind=25 of all states), so finished work fills the lists: on the-job pr shows 3 open in 25 rows and mention 1 in 25 (shots/plan-items-8792-top.png); on the factory gap has 92 parked, 31 merged, 7 closed against 77 open. A filter click (go(), pages.js:614-622 -> replaceRoute, util.js:455 -> refresh()) is not a document load but re-asks items, each kind's items-flow (about 2.5 s each on the-job), the trust table and items-graph one system after another (await in a loop, pages.js:674-678) with nothing shown meanwhile, and the same /api/items went out three times in 7 s (click, then the 4 s poll twice): it looks like a reload that hangs (plan-items-8792-afterfilter.png).
Change: one finished choice for the whole Items page, one address parameter finished=hide|waits|show, read by the list, each kind's section, Graph and Timeline through one helper in pages.js (itemsFinished()); this gap adds hide and show, items-graph-one-show-choice adds waits (which the list treats as hide). The reader's word is 'unfinished' (never 'open', which already means an opened system and an open loop).
(a) server: GET /api/items takes finished=hide|show (default hide). Hidden = the kind's finished states from finish_of (spec/finished.py) plus dead; paused states (parked) stay; a lives-on kind hides nothing. Three things are never hidden, whatever the parameter: an explicit state= (state=closed shows closed); an item set carried by a link (a stock's, valve's or closed box's 'Show them on the Items page': the list shows exactly that set and its count equals the stock's or valve's count); and search matches (q=): a finished match is listed and counted apart ('1 finished match'). Counts per kind and state are unchanged; the answer adds per kind `hidden`. Paging uses the index's states list (spec/items.py _paged / in_states_page), not a filter after the cut.
(b) page: one toggle beside the search, 'Show finished', writes finished=show with replaceState; under each kind a note 'N finished (merged, closed, dead) not shown · show', whose link flips the same page-wide parameter (no per-kind finished control). Defaults, no owner question: dead letters are hidden and counted in the note; parked stays listed.
(c) a click shows 'Loading…' under the heading at once, a newer click aborts the older request (AbortController), the poll never overlaps a pending click, the per-system items-graph requests run in parallel (Promise.all), and a state click within a kind already loaded filters the loaded rows before the server answers. Snapshot mode applies the same filter client side.
Definition of done:
1. /items on a fixture lists no item in a finished or dead state, and each kind with any says how many are hidden and which states.
2. /items?finished=show lists them; the toggle and the note's link write and read the one parameter; no second finished control exists on the page.
3. /items?kind=gap&state=closed on a factory-shaped fixture lists closed gaps.
4. A parked gap is listed by default; dead is hidden and counted in the note.
5. Story F1: searching the id of a finished item finds it, with '1 finished match' said.
6. Story F4: following 'Show them on the Items page' from a stock that counts a finished state lists exactly as many items as the stock's value.
7. With the API delayed 2 s a state click shows 'Loading…' or filtered rows within 100 ms, and exactly one /api/items request follows it; no document load event fires after the first.
8. SPEC §5a documents the default, the parameter and the three exceptions.
Files: ergostat/web/server.py (items handler, _as_listed), ergostat/spec/items.py, ergostat/web/static/pages.js (pageItems default, toggle, itemsFinished, go/refresh), docs/SPEC.md, tests/test_item_sets.py, tests/test_items_page.py.
Acceptance tests: unit listing over gaps in merged, closed, parked, dead, open (default: open and parked; finished=show: all five; state=closed: one; q= of a merged id: found); the item-set count test; browser tests for the note, the parameter and points 5-7.
Budget: 170 net lines.

Milestone: items-page-readable. Owner items: 1. From the owner's list and the design review of 2026-11-22.
