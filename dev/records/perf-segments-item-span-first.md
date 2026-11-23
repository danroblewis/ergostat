# perf-segments-item-span-first: An event query by item skips segments that do not hold the item before testing their types

depends-on: []

Problem: every API answer waits for state.snapshot (1.25-1.6 s on the factory record on an idle thread, 5-15 s under load). A profile on a copy of the factory's state puts 2.5 of 3.5 s in state.explain -> counted -> spec/items.py moved -> _late (spec/items.py:220), which refolds about 1,750 items per snapshot. Each refold is a Segments.query(item=...), and Segments._rows (ergostat/segments.py:436) runs the _types_matcher lambda (segments.py:131-137, 2.1M calls a snapshot) on every segment before it checks s.span(item), which rules out almost every segment.
Change: in _rows check the time and seq ranges, then s.span(item) when an item is given, and only then the types. Optionally cache each segment's matching type list per matcher.
Definition of done:
1. _rows returns the same rows for every argument combination and returns early when the item is not in the segment.
2. A unit test over a record with several sealed segments: a query by item, with and without skip/type, returns exactly the old answer for 50 random items; a counting matcher shows segments without the item are not type-tested.
3. The PR states the snapshot time before and after on a copy of the factory state (ERGOSTAT_HOME pointed at a copy); expected about 1.25 s to 0.8 s.
Files: ergostat/segments.py, its test under tests/.
Acceptance tests: the new unit test; the existing segment and store conformance tests unchanged; a snapshot on a record of 30+ sealed segments at least 30% faster with identical output.
Budget: 20 net lines outside tests.

Milestone: pages-answer-fast. Owner items: 2. From the owner's list and the design review of 2026-11-22.

## Where it stopped

- Done: `Segments._rows` (ergostat/segments.py) now checks the time and seq ranges, then `s.span(item)`, and only then
  tests the types. Both checks only return `[]` early, so moving one ahead of the other leaves every argument
  combination's rows as they were. Net change outside tests: 0 lines (a line moved, with a comment added).
- Not built (the most reversible choice): the optional cache of each segment's matching types per matcher. `_scan`
  makes a new matcher lambda for each call, so a cache keyed on the matcher could pick up a stale entry when an id is
  reused (lesson 5), and a cache keyed on (type, skip) would add lines the definition does not require.
- Tests: tests/test_segments_item_span.py. It builds a record of 12 sealed segments plus a head and keeps the same
  events in SQLite as the old answer. For 50 random items it runs 11 query shapes (type, prefix, skip, n, first, a time
  window, a seq window), and each answer must equal SQLite's. A counting matcher, passed to `_rows` directly and also
  monkeypatched in through `query`, is called only for the types of the segments that hold the item (and the head's).
  With the old order put back, both counting tests failed (60 calls against 5 expected, and 65 against 15); with the
  change they pass. tests/test_store_conformance.py passes unchanged (38 passed; its 7 skips need VictoriaMetrics or
  tiers, which were skipped before this change too).
- Not run here: point 3 (the snapshot time before and after on a copy of the factory state) and the acceptance
  measurement "a snapshot on 30+ sealed segments at least 30% faster". This session could only run named test files
  and ruff (other shell commands were refused), and it has no copy of the factory state. The factory or the
  coordinator must measure both on the branch head before the PR states any numbers. No speed-up is claimed here.

## Where it stopped

Parked by the factory (review/perf-segments-item-span-first-1, 2026-11-22 05:51).

Done: Segments._rows checks the time and seq ranges, then s.span(item), and only then tests types (0 net core lines). tests/test_segments_item_span.py checks the answers against SQLite for 50 items across 11 query shapes, and two counting-matcher tests show segments without the item are not type-tested (reported failing with the old order). Left: point 3 and the acceptance measurement. Someone with a copy of the factory state must time state.snapshot on origin/main and on this branch head (ERGOSTAT_HOME pointed at the copy, a record of 30+ sealed segments), confirm identical output and at least 30% faster, and put the before/after numbers in the PR. It stops here because only the coordinator or factory can take that measurement.

## Where it stopped

Round 2 (2026-11-23). The code and tests are as round 1 left them; nothing was changed. The queue said the readings
that need the factory state belong to the coordinator and are not part of this gap, so this round only ran the
suites again on the branch head (main 69ed1030 merged in): tests/test_segments_item_span.py 3 passed;
tests/test_store_conformance.py 46 passed, 12 skipped (they need VictoriaMetrics or tiers, which are not set up
here; main skips them too); tests/test_mirror.py and tests/test_repair_verify.py (they also build Segments) 63
passed; ruff clean.
The coordinator owes point 3 and the acceptance measurement: time state.snapshot on main and on this branch head
with ERGOSTAT_HOME pointed at a copy of the factory state (a record of 30+ sealed segments), confirm the output is
the same, check it is at least 30% faster, and put the before and after numbers in the PR. No speed-up is claimed
until then.
