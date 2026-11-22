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

## Where it stopped

Round 1. Items 1-3 are built and tested. Item 4 (the timing) is **not measured**: see below.

**Built** (`ergostat/precedence.py`, +13/-4, 9 net lines against a budget of 40):
- Once the capped graph and its links have been read (still under the index lock), every precedence target that
  the graph's items name but the cap cut is read by id in **one** `ix.items(None, ids=cut, moves=False)` call.
  `finished(d)` reads the target's status from the graph or from that lookup. A target found in neither (never
  recorded, or unreadable) is not finished, so it stays in `waiting` and is named there (lesson-3).
- The cut itself is now made in sorted id order, not set (hash) order, so the drawn graph is the same under every
  `PYTHONHASHSEED`, as well as the eligibility. This is the reversible choice: it changes only which items past the
  cap get drawn, and the lookup has made eligibility independent of the cap anyway.
- SPEC (the Items tab bounds paragraph) now says the caps bound what is drawn, never whether an item waits.

**Tests** (`tests/test_precedence_cap.py`; the precedence tests had no single file, so they got a new one). They use
the real `MOST_PULLED` with N = 405 dependencies of a second kind, so the last five by id are cut:
- `test_a_finished_dependency_beyond_the_cap_does_not_block`
- `test_the_result_does_not_depend_on_the_hash_seed` (seeds 0, 1, 7 and 12345 in subprocesses: same eligibility,
  same graph)
- `test_an_unfinished_dependency_beyond_the_cap_blocks_and_is_named`
- `test_an_unreadable_dependency_blocks_and_is_named`

I broke the code and watched the tests fail (lesson-9). Without the lookup, all 4 failed. With a missing target
counted as finished (fail-open), the unreadable test failed. With the cut back in set order, 3 failed, the seed test
among them (4 different graphs across the 4 seeds).

**Bound (item 4), argued and not measured:** the lookup adds one indexed query per look, over the distinct
precedence targets the graph's links name, read in chunks of 500 ids and without their moves. Nothing is read per
item, and nothing past the links already read. I wrote a benchmark (2,000 parts and 300 tickets with 8 dependencies
each, far past 545 first-hop neighbours), but this headless session refused to run it, both as
`timeout 300 uv run python /tmp/bench_cap.py` and as an inline `uv run python -c '...'`. Writing to `/tmp` with the
file tools was refused too, and the factory's own record could not be reached (listing `~` was refused). I did not
run the benchmark through a test to get around those refusals. **Left:** time `precedence.build` (or
`order_ready`) on a copy of the factory's record before and after this branch, and write both numbers here.

**Not run:** the full unit suite under the watchdog, the four browser files, and the merge of origin/main with the
suites run again (the factory runs these after me). Run here, one file at a time: test_precedence_cap,
test_take_order, test_relations, test_relations_asof (35 passed), and test_eta, test_backlog and test_factory
(184 passed, 2 skipped; I did not look into the skips). Ruff is clean.
