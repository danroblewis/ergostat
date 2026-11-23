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

## Where it stopped

Built, round 1 (cd8fc84e). 69 net lines outside tests, docs and dev (budget 100). What was built, and the choices made
alone (each the more reversible one):

- `leased_by` (spec/item_sets.py) answers `taken`, `waiting`, `at` and `set` per block (the old `held` field is gone;
  nothing else read it). A taken item is one whose lease has a holder of that block (`leases.fold.held`), in any state;
  acked or given back, it has none. `waiting`: the kind's items in `takes.at`, matching `takes.where`, not taken (the
  dispatcher's own test, without its busy and not_before checks).
- The set is a new filter on `ItemSet`, `taken=BLOCK` (`/items?kind=K&taken=BLOCK`), read by `parse`, `asked` and
  `select`; with `moved` or a process filter it is refused (BadSet), never silently dropped. The Items page carries it
  in its set address (pages.js: one line; pages.js is not in Files, but without it the line's link would open the
  whole kind). items-list-hides-finished-by-default has not landed, so its item-set rule is not applied.
- The line keeps `.leases-line`, its one link, and `N leased now` (test_items_page.py's
  test_a_valves_leased_items_are_listed_live asserts '1 leased now' and is unchanged), then `; N waiting at STATE` or
  `; none waiting`. Under it the taken list (itemsets.js `takenList`), in both panels (dynamics.js and details.js
  both call countsLines, so neither file changed).
- The run's cell links to `/record?item=ID`: the Record page has no filter by run, so the item's events (the run's
  among them) is the nearest; its title gives the whole run id.
- leaseCells' expiry and attempts cells are now `leaseTail(l, nth)` (pages.js), used by both; the Items page's output
  is unchanged. In the panel the attempt is the one the run is making (`attempt attempts+1 of max`, since a lease's
  `attempts` counts ended ones).
- Polling: the Change says 're-read only while the panel is open and taken > 0', but definition-of-done 3 needs a
  lease taken while the block has taken nothing to appear within 8 s. The list is read every 4 s while the panel is
  open, whatever the count (one small `items` request; it stops when the panel closes). Reversible by one condition.
  The waiting count is the part answer's, as of the panel's opening; the taken count and list are live.
- DoD 5 is checked on the text this change draws (the line and the list): the Dynamics panel's loops paragraph names
  the model's own goals, one of which is `quality-held`, which is the model's text, not the panel's words.

Tests: tests/test_item_sets.py (11 passed; the new test fails with the holder check removed: 2 taken, not 1) and
tests/test_items_page.py whole (24 passed, rc 0, none skipped) under the watchdog; ruff clean. Breaks seen to fail
the browser tests: the unchanged-answer guard removed (the MutationObserver sees a change), the 4 s re-read removed
(hypothesis/4 never appears within 8 s). On main the three browser tests fail (no `.taken-list`) and the unit test
fails (no `taken`; the leased-state count is 0). Not run here: the unit suite, test_diagram_rendering.py,
test_page_polling.py, test_page_refresh.py. Main had no new commits since the branch began, so there was nothing to
merge.

Round 2: main (a08e4b3e) merged in. The two test-file conflicts were both sides adding tests at the same spot; all
are kept. Main's kind page (pages.js `paged()`) asked for the kind without the set's filters, so the line's link
listed the whole kind (test_a_valves_leased_items_are_listed_live failed after the merge). A taken set is now not a
plain kind page (one condition). items-list-hides-finished-by-default has landed: a taken set is answered by
`item_sets.select`, before its rule hides anything, so its Items page lists every taken item, as many as the line
counts, whatever their state (the rule's own case for a stock's link). After the fix: tests/test_item_sets.py 17
passed; tests/test_items_page.py whole under the watchdog: 70 passed, 1 failed. The failure is
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart (the header's project switcher never lists the
other project; it failed three times, once alone). This branch changes nothing it reads (item_sets.py, itemsets.js, the
Items page's set address, style.css). Running it on clean main was refused here, so it is reported, not fixed.
