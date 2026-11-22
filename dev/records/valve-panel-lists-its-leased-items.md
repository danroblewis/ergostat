# valve-panel-lists-its-leased-items: A valve's panel lists the items its block has taken now, counts them right, and says how many wait

depends-on: []

Problem: a valve's side panel says only 'BLOCK works items of kind K: N leased now. Show the leased items' (ergostat/web/static/itemsets.js:86-95 countsLines; used by dynamics.js:613 and details.js:108; server.py:778-780 from spec/item_sets.py:399-410 leased_by). And the count is wrong: on :8794 Dynamics, delivery, valve 'started' reads '0 leased now' while its own 'Items through it' table shows two rows 'leased by developer' and /api/items shows ticket/e203-release in state doing with lease.block developer (shots/plan-ks-road-valve-started.png, reproduced three times). Cause: leased_by builds ItemSet(states=[LEASED], where lease.block=B); once a run's first event moves the item out of 'leased' it is no longer counted though the block still has the lease. The owner wants those items on the valve's sidebar.
Words (docs/vocabulary.md, 'Items and leases'): an item a block has leased is 'taken' or 'being worked by <block>'; 'held' and 'holding' are a goal's words and are not used here.
Change: (1) a taken item is one whose lease has a holder, whatever its state; leased_by counts those per block and returns a set the Items page can open (a taken filter, shown exactly per items-list-hides-finished-by-default's item-set rule when that has landed), plus `waiting` (items of the kind in the block's takes.at states, not taken, matching its where) and `at`; the answer's fields are taken and waiting. (2) in countsLines, for each entry with taken > 0, fetch up to 10 of the set and draw a table under the line 'being worked by developer (3)': id (link to /item/ID), title (itemTitle), its state, run (first 8 chars, link to the Record), taken for, expires in ('overdue 1m' in the bad colour), attempt n of max; reuse leaseCells (pages.js:819) as one helper filed Q30 can use. More than 10: 'all N taken' links to the set. None: 'developer is working nothing now'. (3) the list is re-read every 4 s only while the panel is open and taken > 0; an unchanged answer leaves the DOM alone. Both the Dynamics and the Blocks/classic panels.
Definition of done:
1. leased_by counts items with a lease holder in any state; an acked one is not counted.
2. The valve panel lists each taken item with the facts above in Dynamics and Blocks.
3. A lease taken or ended while the panel is open appears or goes within 8 s without a reload.
4. The line says 'N waiting at STATE' or 'none waiting'.
5. No reader text in the panel contains 'held' or 'holds'.
6. .leases-line and its link remain (tests/test_items_page.py:328 passes unchanged); SPEC §9.5 names the list.
Files: ergostat/spec/item_sets.py, ergostat/web/server.py (part answer), ergostat/web/static/itemsets.js, dynamics.js, details.js, style.css, docs/SPEC.md, tests/test_item_sets.py, tests/test_items_page.py.
Acceptance tests: unit: an item taken then moved to a later state by its run is counted; browser: test_a_valves_panel_lists_each_taken_item (row link href /item/hypothesis%2F1, text contains the block), a lease taken/ended appears/goes, 'working nothing now' with 'waiting at'. Each fails on main.
Budget: 100 net lines.

Milestone: kind-and-item-pages. Owner items: 16. From the owner's list and the design review of 2026-11-22.
