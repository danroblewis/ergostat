# item-page-says-where-it-went: An item says where it went in the model: the stocks it was counted in and the valve and block that moved it

depends-on: [kind-and-item-footprint-api]

Problem: the item page tells leasing three times (the Lease table, 'How it moved' pairs like review -> leased -> done that lose the state it was reviewed in, raw ergostat.lease.* events; shots/plan-ks-road-item-leased.png) and never says which stocks it was counted in, which flows and valves moved it or which blocks took it; nothing links to the diagram. The owner asks for what the item passed through.
Change: a 'Where it went' section after the header of pageItem (ergostat/web/static/pages.js:911), drawn from the `path` of /api/items/ID: one line the stock-and-flow way, in order: [todo 15s] =started (developer, run 2f02cb16, 4s)=> [in-progress 3s] =submitted=> [in-review] ... Each stock and valve is a link to the diagram with that part selected (filed Q36's address), each block a link to its agent page when it exists, each run a link to the Record; the final state is marked; rework shows as a repeated step with its attempt count. The current step of an item being worked says 'being worked by developer for 4m'. It replaces the lifecycle strip for items with a path; kinds nothing counts keep filed Q55's strip (Q55 is amended to cover uncounted kinds only) and say 'not counted anywhere in the model'. The path's current step is where the item is counted, with its link back: this is filed Q58's content, and Q58 is closed as superseded. The Lease table moves under it as a closed details 'Attempts (N)' (with filed Q54); the 'ergostat lease ITEM --redrive' command leaves the reader's text (Q12).
Definition of done:
1. On the roadmap fixture /item/ticket%2F<a done ticket> shows 'Where it went' naming todo, started, developer, in-progress and finished, reviewer, each a link.
2. A taken item's current step shows the block working it and for how long; no text of the section contains 'held'.
3. An item of an uncounted kind shows the sentence and no path.
4. No row of the page reads 'Not held Attempts'; the Lease table is inside the closed details.
5. At 390 px the strip wraps without horizontal scroll.
Files: ergostat/web/static/pages.js (pageItem), style.css, tests/test_items_page.py, docs/SPEC.md §5a.
Acceptance tests: test_an_item_page_shows_its_path (one link per step, in move order); test_an_uncounted_item_says_so.
Budget: 110 net lines.

Milestone: kind-and-item-pages. Owner items: 20 (what it passed through). From the owner's list and the design review of 2026-11-22.
