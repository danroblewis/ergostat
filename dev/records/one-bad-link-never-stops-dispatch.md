# one-bad-link-never-stops-dispatch: a dependency loop through a split parent cannot stop every block in the factory

depends-on: []

On 2026-11-21 at 20:28 the factory stopped taking any work for 30 minutes: no implementor, reviewer, merge-queue, triage or upgrader run started. `ergostat/leases/dispatch.py` logged `leases: KeyError: 'gap/ai-calls-ask-the-budget'` every second (1,901 times). That gap had just been given a dependency on its own split parent (`gap/ergostat-s-own-ai-calls-under-the-budget`). A split parent is a summary that waits on its children, so the child and parent form a loop the graph code in `ergostat/precedence.py` does not expect. `Dispatcher.run` catches the exception and tries again, so the engine stayed "healthy" while doing nothing. The coordinator removed the one dependency by hand and work resumed at once.

## Definition of done
1. `precedence.build` and `order_ready` handle a loop through a parent or a dependency without raising. The items in it are marked as a cycle, are not taken, and name what they wait on.
2. An exception about one item or one block in a dispatcher look never stops the other blocks: it is caught per block, and the rest are still dispatched.
3. A dispatcher error repeating for more than 2 minutes raises a pipeline situation naming the error, and health reports it, so it is not silent.
4. The intake refuses a gap's dependency on its own ancestor (`parent`, at any depth), records it as a `dependency_problem`, and does not write it to `depends_on`.
5. The planner's prompt says a sub-gap never lists its parent in `depends-on`.

## Files to touch
`ergostat/precedence.py`, `ergostat/leases/dispatch.py`, `dev/bin/deps.py`, `dev/bin/watch.py` or `dev/bin/live.py`, `dev/prompts/planner.md`, tests.

## Risks
- lesson-3: an item in a loop is never treated as unblocked.
- Keep the look's time as it is: do not add a whole-record read per item.

## Acceptance tests
- a child depending on its split parent does not raise in `build` or `order_ready`, and is not taken
- a block whose look raises does not stop the next block's dispatch
- a repeated dispatcher error raises a situation
- the intake refuses a dependency on an ancestor and records the problem

## Size budget
70 net lines of code outside `tests/` and `docs/`.

## Where it stopped
Built, round 1: all five points, with the four acceptance tests in `tests/test_one_bad_link.py` (three) and
`tests/test_deps.py::test_the_intake_refuses_a_dependency_on_an_ancestor_and_records_the_problem`.
Overrun reason: 78 net lines outside tests/ and docs/ (28 in ergostat/, 50 in dev/: deps.py 19, live.py 21, watch.py 9, planner.md 1); point 3 needs a carrier the dev/ tools can read (the heartbeat's dispatch_error), a health check, and a watch condition, each small, and the docstrings that say what they guarantee.
Choices made alone (the most reversible):
- The heartbeat (`ergostat/spec/watchdog.py`) carries the dispatcher's standing error, because `live.py health` and
  the watch read only the heartbeat; that file is outside the definition's list.
- "Repeating" means every look meets an error, whatever each one says, timed from the first. A clean look clears it, so
  an error that varies with each look still counts.
- The watch counts the `dispatch` condition at once (like `main-twice`), since the engine has already waited 2 minutes.
  The situation is raised at the watch's next run, while no other situation is raised or leased and no session ran
  within `[manager] broken_minutes` (as for every broken condition), so it can come later than 2 minutes.
- In the watch, an unreadable heartbeat (no instance) is not this condition. An engine with no fresh heartbeat is
  `live.py health`'s `engine` check, and an unreadable heartbeat there fails `dispatch` too.
- Cycles in `precedence.build` now include an unfinished child before its unfinished parent (the edges the critical
  path already used). `relation_cycles` (the whole-record finding) is left at precedence relations only.
Not run: the whole unit suite, the four browser files and demo_check (no example touched). origin/main is not in this
clone and was not fetched (no network); local main is this branch's base.

Round 2 (the fix of review 1):
- Blocking (precedence.py, a parent depending on its descendant): `build` now seeks cycles over exactly the pairs it
  passes to `cpm` (a parent's start and end nodes included, mapped back to the items), and repeats until none is
  found, removing each cycle's items from the projection, so no loop through a parent, either way and at any depth,
  reaches `cpm`. Precedence-only cycles are still found first over every item, as on main. Test:
  `tests/test_one_bad_link.py::test_a_parent_depending_on_its_child_and_a_grandchild_on_its_grandparent_are_cycles_not_taken`
  (a parent on its child, a grandchild on its grandparent, a grandparent on its grandchild: no raise, all marked a
  cycle, each names what it waits on, none taken). Seen to fail with `KeyError: 'gap/k'` with the repeat disabled.
  A cycle also takes in the items between (the middle generation), since they lie on the loop.
- Non-blocking (watch.py, a stale heartbeat): the watch's `dispatch` condition counts only while the heartbeat was
  written within `live.PASS_FRESH` seconds; an older one (or an unreadable `written`) is a dead engine, not this
  condition. Tested in `test_a_repeated_dispatcher_error_raises_a_situation` (seen to fail with the check removed).
- Non-blocking (depth): the new test above covers a grandparent.
- Non-blocking (size): answered below. Left as is: deps.py refuses a dependency on an ancestor only (DoD 4); a
  dependency on a descendant is now a cycle in the graph and is never taken, but the intake still writes it.
Overrun reason: 84 net lines outside tests/ and docs/ (33 in ergostat/: precedence.py 11, dispatch.py 19, watchdog.py 3; 51 in dev/: deps.py 19, live.py 21, watch.py 10, planner.md 1), against 70; outside tests/, docs/ and dev/ (the brief's count) it is 33. Round 2 added 6: the repeat over the critical path's own pairs (5) and the watch's freshness check (1).
Tests run in round 2, one file at a time: test_one_bad_link.py, test_deps.py, test_precedence_cap.py, test_take_order.py,
test_relations.py, test_relations_asof.py, test_eta.py, test_numbers.py, test_graph_cli_web.py (all pass); ruff clean
on ergostat tests scripts. Not run: the whole unit suite, the four browser files, demo_check. Still no origin/main in
this clone (`git branch -a` lists only main and this branch).
