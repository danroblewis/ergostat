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
