# merged-dependencies-never-block: a finished dependency never blocks a gap because the item graph was capped

depends-on: []

Found on 2026-11-21: from 19:10 to 19:37 the implementor took nothing, though gaps with every dependency merged were waiting. `order_ready` (`ergostat/precedence.py`, used by `takes: {unblocked: true}`) reads a graph capped at `MOST_PULLED` (400) linked items. The items are gathered in a set and the first 400 kept, so which are cut depends on Python's string hash order. A dependency cut from the graph is then counted as unfinished (`precedence.py` near line 323), and its dependent is silently skipped. The record's first hop alone had 545 neighbours. A replay of the record found the graph capped under all 12 hash seeds tried, and at 19:36 at least one of two eligible gaps falsely blocked under 6 of them. The problem grows with the record.

## Definition of done
1. In `precedence.build`, a precedence target that is not in the capped graph is looked up by id in the item index, and its real status decides `waiting`. The cap limits what the graph displays and never decides whether an item is eligible.
2. A target that cannot be read at all is still treated as not finished (lesson-3), and is named as what the item waits on.
3. The result does not depend on `PYTHONHASHSEED`.
4. The lookup is bounded: a look over the record stays within its current time on a record of this factory's size, measured and written in *Where it stopped*.

## Files to touch
`ergostat/precedence.py`, `tests/test_precedence.py` (or the file holding its tests).

## Risks
- This runs inside the dispatcher's look: do not read the whole record for each item.

## Acceptance tests
- a gap whose finished dependency is beyond `MOST_PULLED` is eligible, under several `PYTHONHASHSEED` values
- a gap whose unfinished dependency is beyond `MOST_PULLED` stays blocked and names it
- an unreadable dependency blocks the gap and is named

## Size budget
40 net lines of code outside `tests/` and `docs/`.
