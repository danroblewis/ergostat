# gaps-landed-stock: the model has a stock of gaps that have landed on main

depends-on: []

The owner (2026-11-21): "do we have a stock for gaps that have been merged? i see `gaps approved`, i dont see `gaps merged`? or landed?" Today `gaps-merged` in `dev/model/landing.yaml` is only a flow out of `gaps-queued` with no `to:`, so landed work leaves the diagram and no running total is shown.

## Definition of done
1. `dev/model/landing.yaml` has a stock `gaps-landed` (unit gaps), described as the gaps merged on main, with the sensor `{items: gap, state: merged, every: 1m}`.
2. The flow `gaps-merged` keeps its name and equation and gains `to: gaps-landed`.
3. Every other flow that ends a gap in the state `merged` also goes `to: gaps-landed`, including the join judge's flow in `dev/model/knowledge.yaml` (a joined gap found covered), so the stock's balance matches its sensor. Today `gaps-merged`'s sensor also counts joined gaps that `joins-covered` counts, so with both flowing in, a joined gap would be counted twice: resolve that so each landed gap enters the stock once, and every measure that reads `flow.gaps-merged` (`dev/model/measures.yaml`, the upgrades flow) keeps the same reading.
4. The stock has no outflow: it only rises. Nothing in the model treats it as work waiting, so no goal, pool or gate changes because of it.
5. `ergostat check` adds no finding on the factory's model, and the Dynamics diagram draws the stock with the flow into it.

## Files to touch
`dev/model/landing.yaml`, `dev/model/knowledge.yaml`, `tests/test_factory.py` only if it pins the model's stocks.

## Risks
- lesson-3: the stock reads the items' state, so a failed read is no reading, never 0.

## Acceptance tests
- the factory's model loads with `gaps-landed` and the flows into it
- a joined gap that lands enters the stock's balance once
- `ergostat check` on the model reports no new finding

## Size budget
0 net lines of code outside `tests/`, `docs/` and `dev/`.

## Where it stopped

Built, round 1. Nothing is left from the definition. One decision was taken alone (no one to ask), and it is
written here because point 3 can be read two ways.

**What changed.**
- `dev/model/landing.yaml`: the stock `gaps-landed` (unit gaps, system landing, the sensor as point 1 gives it),
  `cumulative: true` (a running total: without it `check` says `stock-without-outflow@stock.gaps-landed`), and
  `gaps-merged` gains `to: gaps-landed`. Its name and equation are unchanged.
- `dev/model/knowledge.yaml`: `joins-covered` (the join judge's flow) gains `to: gaps-landed`. Only these two flows
  have a sensor counting gaps entering `merged`, and the only blocks that move a gap to `merged` are the merge queue
  and the join judge.
- No goal, pool, gate or equation reads `stock.gaps-landed`.

**The decision: how a joined gap is counted once.** The join judge merges a joined gap with `merged_by: join-judge`
(`dev/bin/plan.py`, the covered verdict). Nothing else sets `merged_by`. `gaps-merged`'s sensor is now
`{items: gap, entering: merged, where: {merged_by: null}, over: 1d}`, so it counts the queue's merges, and
`joins-covered` (`join_verdict: covered`) counts the joins. Each landed gap is in exactly one of the two inflows.
No other fix was possible: with both sensors unchanged, a joined gap is counted twice whatever the wiring.
To undo it, drop the `where:`.

What "keeps the same reading" holds for, and what it does not:
- `dev/model/measures.yaml`: every auxiliary there that is `driven-by` `flow.gaps-merged` (cycle-hours,
  size-accuracy, size-accuracy-high, coverage-below-floor) reads its own `measure.py` sensor, which still counts every
  merged gap. They are unchanged.
- `upgrades-opened`: its equation `upgrades-per-merge * flow.gaps-merged` reads `gaps-merged`'s equation, which is
  unchanged, and its own sensor (upgrades entering available) is untouched.
- `gaps-merged`'s **own sensor** reading does change: it reads less by the joined gaps found covered (how many
  that is was not measured here: there is no record in this clone). The flow's equation only ever modelled the queue's merges (`stock.gaps-queued / queue-time`), and a covered
  join pushes no commit (so it opens no upgrade). So the sensor now measures what the equation predicts. Nothing in the
  model reads that sensor except its own fit.

**Tests** (in `tests/test_factory.py`, after `test_the_factory_blocks_take_...`):
- `test_the_factory_model_loads_with_gaps_landed_and_the_flows_into_it`
- `test_a_joined_gap_that_lands_enters_the_landed_stock_once`: two queue merges and a covered join in a real
  project of the factory's model: gaps-merged reads 2, joins-covered 1, the stock 3.
- `test_ergostat_check_on_the_factory_model_reports_no_new_finding` (slow, about 135 s): the real
  `ergostat check --json` on a copy of the model and on the same copy with this change undone. Both sides' extreme-conditions
  tests run whole (`CHECK_WAIT` None, `BOUND` raised, a fresh `ERGOSTAT_HOME`): at check's own 5 s wait, extremes
  kept from an earlier test for one side only made the sets differ in a full-file run. It also draws the Dynamics
  graph and finds the pipes from `gaps-merged` and `joins-covered` into `stock:gaps-landed`.

Seen to fail (lesson-9), each break made on the model and then restored: removing `cumulative: true` fails the check
test (`stock-without-outflow@stock.gaps-landed`); removing the sensor's `where:` fails the joined-gap test (3, 1
instead of 2, 1); removing `joins-covered`'s `to:` fails the load test and the check test
(`move-without-flow@stock.gaps-landed`).

**Not run, or refused.** These commands were refused in this session: `uv run ergostat check --help` (so `check` was
run only through the test, via `ergostat.cli.main`), a scratch pytest file under `/tmp`, `git checkout --
dev/model/landing.yaml` (the breaks were undone by editing), and `git fetch`. The clone has no `origin` remote; local
`main` is already in HEAD, so there was nothing to merge. The unit suite as a whole and the four browser files were not
run here (the factory runs them after). Run one file at a time: `tests/test_factory.py` (129 passed, 2 skipped: the
Docker tests, no Docker in this container), `tests/test_factory_join.py` (6 passed), `tests/test_factory_knowledge.py`
(75 passed), `tests/test_factory_manager.py` (33 passed). ruff clean.

Size: 0 net lines outside `tests/`, `docs/` and `dev/`.
