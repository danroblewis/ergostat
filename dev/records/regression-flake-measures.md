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
