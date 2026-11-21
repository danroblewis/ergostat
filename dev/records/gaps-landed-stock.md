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
