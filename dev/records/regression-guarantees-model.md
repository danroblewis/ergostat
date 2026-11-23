# regression-guarantees-model: The guarantees system: main's failing tests as a stock, held at zero by main-green

depends-on: [regression-flake-main-fixed]

## Problem

When main breaks, the model shows it only as one `main-broken` intervention among the others (dev/model/interventions.yaml:9-12). No stock counts the tests failing on main, and no goal says "main is green" (proposal section 3, F1 row). The proposal's file `dev/model/guarantees.yaml` and its system do not exist (proposal section 6a and milestone gap 5).

## Change

- ergostat.yaml: a system `guarantees` within `oversight` (next to `measures`, ergostat.yaml:55-58), `show: [stock.main-failing-tests]`.
- dev/model/guarantees.yaml (new; `defaults: {system: guarantees}`):
  - stock `main-failing-tests`, `sensor: {items: flake, state: main-broken, every: 1m}`;
  - flows `main-tests-broken` (to it, `{items: flake, entering: main-broken, over: 1d}`) and `main-tests-fixed` (from it, `{items: flake, entering: fixed, where: {fixed_by: main-mend}, over: 1d}`, equation stock / a parameter `main-repair-time`);
  - goal `main-green`: `stock: main-failing-tests`, `hold: "<= 0"`, `tolerance: 0`, `critical: true`, `on-stale: "off"`, `per: item` (docs/SPEC.md:2213-2241);
  - `loops: {main-repair: ...}` naming the balancing loop.
- Wiring: `remedy-when` (dev/model/interventions.yaml:43-50) gains `main: goal.main-green.off`. `remedy`'s `out:` gains `flow.main-tests-fixed`. The block `main-mend` (from regression-flake-main-fixed) gets `out: flow.main-tests-fixed`. The loop closes through people and an existing program. Nothing new acts on the world.
- The owner's question, asked in this gap's "Where it stopped" and not built: should `main-green` off also hold the queue (`queue-when`, dev/model/landing.yaml:309-319) for batches that do not touch the failing tests?

## Definition of done

1. The system and file exist. `ergostat check` on ergostat.yaml reports no errors and no missing feedback for `main-green`.
2. `main-repair` is drawn balancing (`check` says so).
3. A `flake.main-broken` turns `main-green` off. Its `flake.main-fixed` turns it holding again.
4. A stale reading counts as off.
5. dev/README.md has a short section "Regression guarantees" that later gaps extend.

## Files to touch

ergostat.yaml, dev/model/guarantees.yaml (new), dev/model/interventions.yaml, dev/model/landing.yaml (main-mend's `out:`), dev/README.md, tests/test_factory.py.

## Acceptance tests

- `test_the_guarantees_model_checks_clean` (the pattern of tests/test_factory.py:3774-3787: `spec.loop("main-green").closes`)
- `test_main_green_goes_off_and_holds_again` (a break, then its main-fixed, folded on a factory fixture)
- `test_main_green_stale_is_off`

## Size budget

40 net lines of code outside tests/ (the rest is model YAML in dev/).

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
