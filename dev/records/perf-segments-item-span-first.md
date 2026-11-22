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
