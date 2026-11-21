# a-set-chosen-in-a-snapshot: a snapshot holds every set its own answers link to (each part's side-panel set, each process map node's and line's), both as the side panel lists it and as the Items page shows it
depends-on: []

The gap (GAPS, *A set chosen in a snapshot*; its entry was written on `a-kind-chosen-in-a-snapshot` and is not on main yet, so this branch adds it). A set's parameters are free, so not all of them can be held ahead of time. Instead the snapshot holds exactly the sets that the snapshot's own answers link to (an allowlist, read from what it already holds). Those are the only sets a reader of the file can reach without typing an address. On main already, not to be rebuilt: `snapshot.key` / the page's `snapKey`, `_requests` (every `part/K/N` and every `graph?view=process[&system=S]`), `item_sets` and the `items` API's set queries.

## Definition of done
1. **The sets named.** The sets come from answers already in the snapshot: each `part/*` answer's `items.set` (`server.py _items_of`), and each `graph?view=process` answer in it, read the way `process.js` reads them. A node not of kind `schedule` gives `through`. A `related` line gives its first end's `through`. A `caused` line gives `caused` on its target's kind. Any other line gives `followed`. Each carries the map's `by` and its `moved_since`/`moved_until`, written as `pmStamp` writes them.
2. **Both requests held for each.** For every set named, the snapshot holds two answers:
   - the side panel's list: the set's params with `alone=1&n=10&shown=1`, as `itemsets.js itemsSection` asks;
   - the Items page opened from the panel's link: what `pageItems` sends in a snapshot for that address (kind, the set's params, and `state` when the set has one).
   Each is held under the key the page's `snapKey` makes for that request, and holds what the live server answers to it. A parameter with several values (two `where`) is keyed as the page keys it, `a,b`, not Python's `['a', 'b']`.
3. **Opened from the file**, a stock's or a flow's side panel lists its items, a process map node's or line's panel lists its items, and each panel's "Items page" link shows that set. None of these says "not in this snapshot".
4. **A ceiling.** The sets held are at most a named hard maximum (no more than 400). They are taken in a fixed order: parts first, then process nodes, then lines by count, most first. Sets past the maximum are never asked for. A set that cannot be answered (`BadSet`) is left out, and the page says "not in this snapshot" for it as now.
5. **Docs say exactly that.** SPEC's snapshot paragraph (§5a, near "holds the Graph and the Timeline") and the GAPS entry say which sets are held: those its panels link to, up to the maximum. GAPS keeps as *left*:
   - a set typed in by hand;
   - the process map's other `by`;
   - item pages past the 40 held;
   - the entry's second half (a kind of more than 500 items held as its first 500, with "All N" showing the same 300). That half concerns a kind's own list, held by `a-kind-chosen-in-a-snapshot`, which is not on main.

## Files to touch
- `ergostat/web/snapshot.py` (the sets named, held, keyed, capped); if it grows past ~150 lines, the set-naming moves to a new `ergostat/web/snapshot_sets.py`
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/cli-rounds.md` (the snapshot line)
- `tests/test_snapshot_sets.py` (new), `tests/test_items_page.py`, `tests/test_diagram_rendering.py`

## Risks
- lesson-4: the process map gives up to 60 + 160 sets, each held twice. Without a hard maximum, a busy model's snapshot balloons in size and build time.
- lesson-8: "a set chosen in a snapshot works" is wider than the truth. The docs must say "the sets its panels link to" and name what stays unheld.
- lesson-9: a key built in Python that differs from `snapKey` passes every test that only reads Python's own keys back. The tests must use the page's keys, or open the file in a browser, with a set of two `where` values.

## Acceptance tests
- `tests/test_snapshot_sets.py::test_each_parts_set_is_held_as_the_page_asks`: a model with a stock whose sensor matches two `where` values and a flow with a `moved` set. Both requests per set are present under the page's keys (written out literally, `where=f:a,f:b`) and equal the live `api` answer. It fails if lists are keyed by `str()`.
- `tests/test_snapshot_sets.py::test_each_process_map_set_is_held`: for every node and line of each held process map, the `through`/`followed`/`caused` requests are present, with `pmStamp`-form times, and equal the live answer. It fails if a line kind is skipped or the times are written differently.
- `tests/test_snapshot_sets.py::test_the_sets_held_stop_at_the_maximum`: with the maximum patched to 3, exactly 3 sets are held, the first three in the stated order. A counting `api` shows no request past them.
- `tests/test_items_page.py::test_a_snapshot_lists_a_parts_items_and_opens_its_set`: from the file, a stock's panel lists its items. Following its link shows those ids on the Items page, and the page never says "not in this snapshot".
- `tests/test_diagram_rendering.py::test_a_snapshot_lists_a_process_lines_items`: from the file, a process line's panel lists its items, and its Items page link shows them. No "not in this snapshot", no page errors.

For each test, the report says which break was made to the code and that the test then failed.

## Size budget
120 net lines

## Notes from the plan review (answer each)

- Duplicates: the same set can come from a part and from a node or line. Say whether it is held once and counted once against the maximum; the ceiling test should include a duplicate so a double count shows.
- Fixed order: the order of process nodes, and of lines with equal counts, is not stated (by id? as the map answer lists them?). Name it, or the 'first three in the stated order' test has no single right answer.
- Fail-open (lesson-3): only BadSet is left out. Any other error from the api while building the snapshot must stop the build, not quietly drop the set. Add a test where the api raises something other than BadSet and the build fails.
- Browser coverage: DoD 3 names a flow's panel and a process node's panel, but only a stock and a line get a browser test. Add a node (and a flow) to one of the browser tests, or explain why the Python key tests are enough for them.
- Left-out set: add one test that a set dropped for BadSet, or past the maximum, still shows 'not in this snapshot' and does not cause a page error, as DoD 4 promises.
- Size budget: 120 net lines for the code, a new test file with three tests, two browser tests and three docs looks tight. If it runs over, say so in the report rather than cutting the tests.

## Where it stopped

Round 1. Built: `ergostat/web/snapshot_sets.py` (new, 75 lines) and two lines in `snapshot.py`, 77 net lines out
of the 120 budgeted. The docs (SPEC §5a, GAPS, cli-rounds) and the tests are written. **Not run: the three browser
tests**, because this container has no Playwright and `uv run --with playwright==1.63.0` was refused. They are
`tests/test_items_page.py::test_a_snapshot_lists_a_parts_items_and_opens_its_set`,
`::test_a_set_left_out_of_a_snapshot_says_so` and
`tests/test_diagram_rendering.py::test_a_snapshot_lists_a_process_lines_items`. No break was made against them
either. Still to do: run them with the browser suite, and make their lesson-9 breaks (e.g. `MOST = 0` must fail
the first and the third). The unit suite and `origin/main` were not run or merged here: this clone has no `origin`,
and its local `main` is the branch's own base.

Answers to the plan review:
- **Duplicates**: a set is keyed by the page's key of its Items request. It is held once and counted once against
  the maximum. The ceiling test's model has two stocks with the same sensor (`awaiting`, `awaiting-too`), plus each
  stock's sensor part, so a double count fails it. Shown by a break: with dedup removed, it fails.
- **Fixed order** (named in the module's docstring and in SPEC): parts as `_requests` asks them (the tables'
  order). Then each held map's nodes as the map answer lists them, maps in request order. Then all the maps' lines
  together by count, most first; a stable sort keeps equal counts in the order the maps list them. The ceiling
  test takes the map's first node as the third set.
- **Fail-open**: only `BadSet` drops a set. Any other exception, or an answer of None, stops the build
  (`test_a_set_that_is_not_one_is_left_out_and_any_other_failure_stops_the_snapshot`; broken by catching
  `Exception`, it fails).
- **Browser coverage**: the parts test opens a stock and a flow, a disturbance in this model. The process test
  opens a node, a caused line and a follows line, then follows the follows line's link.
- **Left-out set**: `test_a_set_left_out_of_a_snapshot_says_so` (browser, `MOST = 0`), and in Python the `BadSet`
  half of the fail-open test.
- **Size**: within budget.

Choices made alone (the most reversible): the set's key joins a list with commas, as JavaScript's `String` does.
`snapshot.key` is not changed; `snapshot_sets.flat` does the join. Times are written as `pmStamp` writes them,
truncated to the second. A `BadSet` set still counts against the 400. The leased-items link in a flow's panel is
not held: the DoD names only `items.set`, and GAPS lists it as left. Lesson-9 note: a related line's set is its
first end's node set, which is always held, so swapping its end passes `test_each_process_map_set_is_held`. The
breaks that make that test fail are a skipped `caused` line and times written `+00:00`.

Round 1, after the fast suites. `unit` failed one test,
`tests/test_reload_safety.py::test_a_reading_is_never_left_under_way_when_writing_it_fails` (1 failed, 1946
passed). It is not this gap's, and it is left unfixed here (lesson-13). This branch touches no file it runs: it
changes `ergostat/web/snapshot.py`, `snapshot_sets.py`, docs and tests only, and the test runs
`ergostat/spec/engine.py`. By reading, the failure is a race in the test's timing (lesson-10), not in the engine.
The test expects its first `e._readings(False)` only to hand the reading to the pool. But `_begin` submits it, and
`_take` then drains `self.results` (`engine.py:1351-1355`). Under `-n 8`, the pool thread can read the small
model's sensor and put its result before that drain. Then the first call gathers it, and the patched `add_many`
raises at test line 262, outside the `pytest.raises` meant for the second call. In both orders the engine does what
the test is named for: `_take`'s `finally` (l.1370-1374) lets go of the reading. So no engine code is wrong to
fix. The test needs a fix in its own gap: hold the pool's read until the first call returns, or accept the raise
on either call. Not run here: the test alone, to confirm the race (Bash was refused this round). This note is not
committed for the same reason.

Round 1, second fast-suite failure. The `unit` tail given stopped at 10% with no test named. Run again here, serially
and in five chunks (`tests/test_[a-c]*`, `[d-i]`, `[j-q]`, `[r-s]`, `[t-z]`): 1947 passed, 69 skipped, 1 failed. The
one failure is again `tests/test_reload_safety.py::test_a_reading_is_never_left_under_way_when_writing_it_fails`
(`RuntimeError: database is locked` raised from test line 262, the first `_readings` call). Its file alone passes (7
passed). So it depends on timing even without `-n 8`: the pool thread finishes the read before `_take` empties
`results` (`engine.py:1351-1355`), as said above. `git diff main...HEAD` touches neither `ergostat/spec/engine.py` nor
that test. So no code of this gap is wrong, and nothing is changed for it here (lesson-13). The test needs its own
gap: it should block `_read_one` until the first `_readings` returns. Not done: the browser files with playwright,
and a merge of `origin/main` (this clone has no `origin`).
