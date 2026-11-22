# ui-a-filter-that-matches-nothing-says-so-with-a-way: A filter that matches nothing says so, with a way to clear it

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q32 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /record, /items

**The problem:** The Record answers 'Nothing recorded yet.' to a filter that matches nothing. On Items 'Nothing matches.' is printed about 3000 px down, under every chart, so the search seems to do nothing; the chart and heading still show all items.

**The change:** Record: 'Nothing matches "x" · clear'. Items: print the match count or 'nothing matches' beside the search box, and hide kinds (with their charts) that have no match while a search is active.

**User stories it serves:** C5, F1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On /record with filter 'zzz' the page contains 'Nothing matches' and a control that empties the filter; on :8791/items typing 'zzqx' shows 'nothing matches' within 100 px of the search box and no chart; typing 'SCRUM-2' shows '1' beside the box and one ticket row.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
