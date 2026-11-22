# ui-agents-each-row-says-how-it-is-engaged-and-which: Agents: each row says how it is engaged and which goal it serves

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q38 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents; agent panel

**The problem:** A blank 'runs when' cell means on demand; the panel says 'Runs: not run by ergostat' beside '28 runs, 0 failed'; roles name valves, never goals ('valve work'); '0 failed' hides that most runs were refused.

**The change:** 'runs when' reads 'on demand, per item (leased)' when blank. The panel line becomes 'started per item by its lease, not on a schedule'. Roles read 'valve work → goal located-worked'. The run tally reads '28 runs: 9 done, 19 refused (workspace pool full), 0 failed'.

**User stories it serves:** D1, D2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/agents no 'runs when' cell is empty; the 'work' row contains 'on demand' and a goal name; its panel does not contain 'not run by ergostat'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. About 33 net lines outside `tests/` (git diff --stat: 48 added, 15 removed in ergostat/).

What changed:
- `ergostat/web/static/pages.js`: a blank 'runs when' reads 'on demand, per item (leased)' for a block that takes items,
  'on demand' for any other agent ergostat runs, 'by a person' for a person, 'not run here' otherwise (the last-run
  column's words). Roles go through `rolesText`: a valve reads 'valve work → goal located-worked'.
- `ergostat/web/static/details.js`: the panel's 'runs' line reads 'started per item by its lease, not on a schedule'
  for a leased block ('on demand, not on a schedule' for another one ergostat runs; 'not run by ergostat' stays only for
  agents with no command). The tally reads 'N runs: D done, R refused (workspace pool full), F failed'; the refused
  clause shows only when R > 0.
- The data the page needed was not in the snapshot, so it touches files outside `ergostat/web/` (the definition names
  only the web files; this is the smallest data change that makes the page true):
  - `ergostat/state.py`: each agent gets `leased` (its block has `takes:`), and each valve role gets the `goal` of its block.
  - `ergostat/store.py` and `ergostat/segments.py`: `runs()` also returns `pool_full`, the agent.ran events whose note is
    the PoolFull message ('workspace pool X has none free for ...', `workspaces/pool.py:157`). These are the runs the
    engine gives back without counting them as failed (`spec/engine.py:1165-1171`). Segments count it in a new tally,
    `full`. A segment sealed before that tally existed has no header entry for it, so it is counted from its rows,
    never read as 0.

Most reversible choices, made with nobody to ask: pool-full runs are found by the engine's existing note text, not by
a new field in the record, so old records count too and the engine is unchanged; the CLI's `ergostat agent` table is
unchanged (the definition names only the page and panel).

Tests (`tests/test_agents_page.py::test_each_row_says_how_it_is_engaged_and_which_goal_it_serves`, and in
`tests/test_store_conformance.py` the updated `test_valves_controllers_and_runs` plus
`test_a_segment_sealed_before_the_pool_full_tally_is_read_not_counted_as_none`). The acceptance check runs on a small
model of its own with a leased block `work` (goal `located-worked`), not on a server at :8791. Each one was seen to fail
when its code was broken: blank 'runs when' fallback → the browser test fails; no goal in the roles → it fails;
segments' pool_full set to 0 → the browser test and the segments conformance test fail; SQLite's pool_full set to 0 →
the SQLite conformance test fails (the page's project runs on segments); the old-header guard removed → the
sealed-segment test fails with KeyError.

Run here: tests/test_agents_page.py (4 passed, under suite_watch with Playwright, rc 0, none skipped),
tests/test_store_conformance.py (36 passed, 7 skipped: the existing VictoriaMetrics and tier tests, which need a server),
tests/test_runner_and_state.py (43 passed), tests/test_graph_cli_web.py (31 passed), and ruff (clean). Not run here:
the whole unit suite and the four browser files (left to the factory and the merge queue). main is already an
ancestor of the branch, so there was nothing to merge.
