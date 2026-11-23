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

## Where it stopped

Built, round 1 (2026-11-23). Choices made with no one to ask, each the most reversible, and the done items they touch:

- **remedy is the one setter of `main-tests-fixed`; main-mend's `out:` is unchanged.** The Change gives the flow two
  setters (remedy and main-mend). `check` refuses that: `two-actuators`, "one block sets a flow (put a select in
  front, or split the flow)". `main-mend` keeps `out: flow.flakes-mended`, and dev/model/landing.yaml is untouched.
  The flow's sensor still counts main-mend's own `flake.main-fixed` (`fixed_by: main-mend`). So main-mend is what
  records each fix, and the coordinator (remedy) is drawn as what moves it. The other way is a select in front of the
  flow, or two flows. That is for the owner.
- **No `per: item` on `main-green`.** `check` refuses `per: item` on a count of items (`goal-per`, SPEC §8: "each
  item counts one"), so done item 1 could not hold with it. Without it the goal holds the count at 0, which is the
  same promise. `breaking` does not list the tests; `ergostat item --kind flake --state main-broken` does.
- **`remedy-when` is a `select` (`pick: max`) and no longer an `expr`.** It still gives `max(rising, many, main)`.
  An `expr`'s sign is never known (SPEC §12a), so main-repair would be drawn `?` and not B, and done item 2 would fail.
  A select passes +. One difference: a select ignores an input that is not known, where the expr gave no command at
  all. remedy's `ask` also says what to do about a failing test on main.
- **Done item 2, "`check` says so".** check's feedback list prints the first 12 of `causal.loops`, which stops at 300
  loops. In the factory's model main-repair is past that limit, so check's text does not print it. The test builds the
  cycle from ergostat's own links (`causal.links`), and names and signs it with check's naming (`causal._named`):
  `main-repair`, B. `ergostat check` itself was not run here (the command was refused in this session); the tests read
  the model with `ergostat.spec.read`, which is what check uses.
- **Done item 4 holds only for a reading that can go stale.** An `items` sensor is never stale (SPEC §9.6,
  `observer.stale_by`), so `on-stale: "off"` on main-green changes nothing today. `test_main_green_stale_is_off` pins
  that, then makes the reading stale the way a periodic sensor's would be (it monkeypatches `stale_by`). It shows that
  main-green then counts as off, and that it holds again after a fresh reading. Making items sensors go stale is an
  engine change for every model and outside this gap.

The owner's question, not built: should `main-green` off also hold the merge queue (`queue-when`,
dev/model/landing.yaml) for batches that do not touch the failing tests?

Size: 0 net lines of code outside tests/, docs/ and dev/ (4 lines of ergostat.yaml, the rest model YAML and the
README).

Round 1, the `check` finding sent back (`interface system.guarantees`):

- **main-green's actuator is a person block inside `guarantees` (`fix-main`), not `remedy`.** `remedy` (system
  `interventions`) moving `flow.main-tests-fixed`, the valve of main-green's own loop, is an outside block reaching
  into the system's internals (ergostat/spec/architecture.py, `interfaces`). Every wiring the Change asks for in
  interventions.yaml would trip it: `remedy` moving the flow, or `remedy` commanding a block in the loop. So
  `fix-main` (person, the coordinator, `in: goal.main-green.off`, `out: flow.main-tests-fixed`, with the ask that
  `remedy` had for a failing test) closes main-repair. `remedy-when` loses its `main` input, `remedy` loses
  `flow.main-tests-fixed` and that half of its ask. `remedy-when` stays a `select` (`pick: max`) of its two inputs: the
  same as before for those two. Put it back as an `expr` if you want. This supersedes the first bullet above: remedy is
  no longer main-tests-fixed's setter, and main-mend's `out:` is still unchanged. To reverse it, move `fix-main`'s ask
  back into `remedy`. That brings the finding back, unless the owner allows it (`allows-findings`).
- `test_the_guarantees_model_checks_clean` now asserts that no `interface` problem is about `system.guarantees`
  (`read` runs the architecture findings). It also asserts the loop's actuator is `fix-main`, and walks the cycle
  stock → goal → fix-main → flow as B.
- Not run in this session: Bash was refused for every command ("don't ask mode"), so `ergostat check`, the tests, ruff
  and `git commit` were not run. The edits are in the working tree, uncommitted.
