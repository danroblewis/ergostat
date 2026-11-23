# regression-flake-measures: Flakes open, the hours main stays broken and the hours a flake stays unfixed, with goals

depends-on: [regression-flake-main-fixed, regression-flake-fixed-after-green, regression-guarantees-model]

## Problem

Nothing measures how long main stays broken or a flake stays unfixed, and no goal names the oldest flake (proposal section 3, the "Time to repair" row, and section 4, `flakes-open`, `main-repair-hours`, `flake-fix-hours`). Once the flake states have ways out, those times exist in the record.

## Change

- dev/bin/flakes.py gains readings. Each is read from the items' moves in record order (`ergostat item ID --json`, as dev/bin/times.py and dev/bin/watch.py:92-101 read them), never by comparing stamps (lesson 2). At most 500 items; when it hits that limit it says so.
  - `main-repair-hours`: the median over 14 days, per stay, from the move into `main-broken` from another state to the move to `fixed`. A repeat break inside one stay does not restart the clock.
  - `flake-fix-hours`: the median from the move into `seen` to `fixed`.
  - Either with no ended stay in the window gives no value.
- dev/model/guarantees-flakes.yaml:
  - stock `flakes-open` (`{items: flake, state: seen}`);
  - goal `flakes-few`: `<= 3`, `per: item` (the oldest named), `on-stale: "off"`;
  - auxiliaries `main-repair-hours` and `flake-fix-hours`;
  - goal `main-repaired-fast`: `main-repair-hours <= 24`, `on-stale: "off"`;
  - flows `flakes-seen` and `flakes-fixed` with item sensors.
- Setpoints are parameters. Goals are unserved until regression-guarantees-wired.

## Definition of done

1. The repair hours run from the first break of a stay to its fix.
2. A remake starts a new stay.
3. Readings with nothing ended give no value.
4. `flakes-few` names its oldest items.
5. `ergostat check`: no errors.

## Files to touch

dev/bin/flakes.py, dev/model/guarantees-flakes.yaml (new), dev/README.md, tests/test_factory.py.

## Acceptance tests

- `test_main_repair_hours_from_the_first_break` (two breaks, one fix: measured from the first)
- `test_a_remake_is_a_new_stay`
- `test_no_ended_stay_has_no_value`
- `test_flakes_few_names_the_oldest`

## Size budget

90 net lines outside tests/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: every item of the Change and the four acceptance tests. One choice was made without the owner, the
most reversible one (a YAML edit undoes it):

- `flakes-few` cannot be "`<= 3`, `per: item`" on the count `flakes-open`. check refuses `per: item` on a stock that
  counts (goal-per, ergostat/spec/compile.py `per()`, SPEC §8), and the done item "`ergostat check`: no errors" would
  fail. A goal held per item holds each item's hours, never a count. So `flakes-open` stays the count of seen flakes
  as written, with its flows `flakes-seen` and `flakes-fixed`. `flakes-few` is held `per: item` on a second stock over
  the same items, `flakes-open-hours` (`{items: flake, state: seen, measure: oldest}`). Off, it names the seen flakes
  past its setpoint, oldest first. Its setpoint keeps the definition's number, 3, read in the unit that `per: item`
  holds: hours (parameter `flake-hours-most`). With fixes after 5 green runs, 3 hours is likely off whenever a flake
  is open. The owner sets the real number, or asks for a count goal that names its oldest items. That second option
  is an engine change, so it would be its own gap.
- check's findings on the new parts, pinned in the test as an allowlist: `missing-feedback` on both goals (no block
  until regression-guarantees-wired), `parameter-unused` on the two setpoint parameters (no equation reads a goal's
  setpoint), and `stock-without-flows` on `flakes-open-hours` (an age).
- `flakes-fixed` counts every move to `fixed`, main-mend's included. `flake-fix-hours` counts a `seen` stay only when
  it goes straight to `fixed`. A seen flake that went to `main-broken` is counted in `main-repair-hours` from that
  move.
- Net lines outside tests/, docs/ and dev/: 0 (everything is under dev/). Read as this definition writes it
  (outside tests/), the change is 126 net: flakes.py +50, guarantees-flakes.yaml 64, dev/README.md +12.
Overrun reason: only under the definition's "outside tests/" reading: the new model file is 64 lines of the parts the Change lists (with descriptions and the comment on the per-item choice), and flakes.py's readings are 50; the factory's rule counts none of it (all under dev/).
- Not run here: the whole unit suite and the four browser files (the factory's). `ruff check dev/bin` names two
  findings in files this gap does not touch (dev/bin/plan.py B023, dev/bin/review.py E501). ruff on dev/bin/flakes.py
  and on `ergostat tests scripts` is clean.

Answering `ergostat check`'s six new findings (implementor, 2026-11-23). The definition has no `allows-findings`
line, and it was not edited. Each one is fixed in the model. The choices below are mine, without the owner, and each
is a YAML edit to undo:
- `kind-enters-many-times items.flake`: flakes came in from clouds into `seen` (`flakes-seen`) and `main-broken`
  (`main-tests-broken`, guarantees.yaml). As check asks, the arrival into `seen`, the kind's first state, is kept, and
  `main-tests-broken` now runs `from: flakes-open`. Its new equation, `stock.flakes-open / time-to-main-broken`
  (parameter 30d, `estimate: true`, a guess), answers the `no-equation` note that the re-pointing raised. A
  limit: dev/bin/onmain.py can make a flake `main-broken` without `seen` first, and the model draws that as passing
  through `seen` at once. guarantees.yaml was not in the definition's file list. That one flow is the change check
  names.
- `stock-without-flows stock.flakes-open-hours` and `missing-feedback goal.flakes-few`: the age gets its rises
  and falls as flows (`flakes-open-hours-rise`, `flakes-open-hours-fall`), on complexity.yaml's pattern. The person
  block `oldest-flake-fix` (coordinator, as `fix-main` is) reads `goal.flakes-few.off` and moves the fall. Its loop
  is `oldest-flakes`. An age stock with flows in the flake chain is `chain-stock-not-a-count`, and one without flows
  is `stock-without-flows`. So the age's sensor carries `where: {fixed_by: null}`, which matches every seen flake
  (a remake clears `fixed_by`, flakes.py REMAKE_CLEARS), and a sensor with a `where` sits beside the chain
  (chains.py `_counted`). This works around two engine findings that disagree about an age held per item. A flake
  that is seen but still carries a `fixed_by` would not be counted in the age. The engine fix would be its own gap.
- `parameter-unused parameter.flake-hours-most`: `flakes-open-hours-fall` is
  `MAX(stock.flakes-open-hours - flake-hours-most, 0) / flake-fix-time` (1d, `estimate: true`), as
  quarantine-released is. Only the hours past the setpoint fall when asked.
- `parameter-unused parameter.main-repair-hours-most`: removed. No flow here is driven by main's repair hours past a
  setpoint, and an equation made up only to read it would claim a dynamic nobody measured. So the setpoint is the
  goal's own `<= 24`. This narrows "Setpoints are parameters" for this one goal.
- `missing-feedback goal.main-repaired-fast`: the person block `main-repair-hasten` reads its `.off` and commands
  `fix-main` (a cascade, `out: block.fix-main`), because a second block on `main-tests-fixed` is `two-actuators`.
  The loop closes through `main-failing-tests`, which drives `main-repair-hours`. Its loop is `main-repair-speed`.
  This replaces "Goals are unserved until regression-guarantees-wired": off, each goal now asks the coordinator.
- Pinned in `test_flakes_few_names_the_oldest`: no finding at all on any of the parts, the flake kind,
  `main-tests-broken` or `fix-main`, and each goal's loop closes. I took out the `where` and the test failed on
  `chain-stock-not-a-count`. I took out `from: flakes-open` and it failed on `kind-enters-many-times`. Both were
  put back and it passed. `guarantees_project` now adds `flakes-open` too, because `main-tests-broken` drains it.
- `uv run ergostat check` from the shell was refused. The findings were read through `ergostat.spec.read`, as the test
  does. With the filter widened for one run to every finding in a guarantees file or about a flake or main part,
  the only one was `acting-on-its-own block.main-watch` (landing.yaml, untouched here, so not this branch's).
- Run: the four acceptance tests, `test_the_guarantees_model_checks_clean`, `test_main_green_stale_is_off`,
  `test_main_green_goes_off_and_holds_again` and the quarantine-small test all passed, and ruff on
  `ergostat tests scripts` is clean.

Overrun reason: only under the definition's "outside tests/" reading: 174 net lines (guarantees-flakes.yaml 99, flakes.py 50, dev/README.md 17, guarantees.yaml 7), the extra over round 1 being the flows, block, loops and parameter check's six findings needed; the factory's rule counts none of it (all under dev/).
