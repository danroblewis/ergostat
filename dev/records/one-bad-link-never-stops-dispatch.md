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
