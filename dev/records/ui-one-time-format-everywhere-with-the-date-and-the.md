# ui-one-time-format-everywhere-with-the-date-and-the: One time format everywhere, with the date and the zone

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q34 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /record, loop panel crossings, /items, /item/…, request pages

**The problem:** Four formats, one with a zone: '04:04:36' (Record), '11/22/2026, 03:27:22' (item), 'Nov 22, 03:55' (list), '2026-11-22T11:22:55Z' (a field, 8 h away). Fields print epoch seconds as '1,795,346,621'; event data rounds them to 6 digits ('1795350000').

**The change:** One formatter: '2026-11-22 04:03:55 PST' (the zone's short name; the date dropped only inside a table whose caption gives it). Format every *_at, raised, since and started field with it. Print event data unrounded.

**User stories it serves:** C5, F2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On /record, /item/ticket%2FSCRUM-2 and a goal's Crossings every time matches /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+/ or sits in a table whose caption carries the date and zone; no cell matches /1,7\d\d,\d{3},\d{3}/; 'done_at' in Events equals the field's value.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
