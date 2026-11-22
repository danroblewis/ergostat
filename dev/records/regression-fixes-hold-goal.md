# regression-fixes-hold-goal: The repair template's goal that no fix regressed in the last 14 days, and the stock in SPEC's parts table

depends-on: []

## Problem

The repair template has the stock `regressed-fixes` and the flows `fixes-regressed` and `fixes-reverted` (ergostat/library/templates/repair/template.yaml:49, :63-64). Its only goals are `no-open-failures` and `fixes-answered` (template.yaml:66-67), so a fix that regressed breaks no goal. A goal on the stock itself could never recover: a denied `revert-fix` leaves the failure `regressed` for good (docs/SPEC.md:6710). SPEC's parts table leaves the stock out (docs/SPEC.md:6723). (Proposal section 3, the U3 row; milestone gap 7.)

## Change

- template.yaml: an auxiliary `fixes-regressed-recent`, `sensor: {items: ergostat.failure, entering: regressed, over: 14d}`, `driven-by: +flow.fixes-regressed`, and a goal `fixes-hold`: `<= 0`, `tolerance: 0`, `on-stale: "off"`. It recovers when a window passes with no new regression. It is served by the existing revert ask: each regressed fix already has its revert asked as a gated action (docs/SPEC.md:6278-6293 area, the repair section). If `check` finds no block serving it, the template's person approver block reads it.
- SPEC section 12r: the parts table lists `regressed-fixes`, `fixes-regressed-recent` and `fixes-hold`, and says why the goal is on the window, not the stock.

## Definition of done

1. A model using `repair` gets `fixes-hold`. A regressed fix turns it off. It holds again after a window with none.
2. `ergostat check` on a model using the template reports no errors and no missing feedback for it.
3. The SPEC table matches the template.

## Files to touch

ergostat/library/templates/repair/template.yaml, docs/SPEC.md, tests/test_repair_verify.py.

## Acceptance tests

- `test_a_regressed_fix_turns_fixes_hold_off`
- `test_fixes_hold_recovers_after_the_window`
- `test_a_denied_revert_does_not_hold_it_off_for_good`

## Size budget

25 net lines outside tests/ and docs/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. Choices made without the owner, each the most reversible:

- **Engine files outside "Files to touch".** The sensor the Change names (`entering:`/`over:` on an auxiliary) was
  refused by compile (`items-on-stock`: only a flow could count moves). Smallest fix: an `items` sensor on an
  auxiliary that names `entering:` or `leaving:` counts the moves over `over:` (ergostat/spec/compile.py, counts.py,
  items.py: the window is used when the sensor names a move, not only on a flow). Its reading is how many moved, not a
  rate per hour, so `fixes-hold` reads in failures. Flows are unchanged (still per hour). An auxiliary with `over:` and
  no move is still refused. SPEC section 6's sensor table says so. Net code lines outside tests/docs/dev: 9, within
  the 25 budget.
- **Which block serves it.** The template has no person approver block (the approver is the gate on the actions), so
  `repair-settle` reads the goal (`in: goal.fixes-hold`). It is the block that asks each regressed fix's revert. `check`
  then finds the loop closed through `flow.fixes-regressed`. Its schedule and commander are unchanged (30 s, the
  implied on-off of `fixes-answered`); the goal only appears in its run's context.
- SPEC's parts table now matches the whole template, not only the three parts named: it adds the auxiliaries row,
  the `fixes-verified`/`fixes-regressed`/`fixes-reverted` flows and `revert-fix`, and drops "(cumulative)" on
  `applied-fixes`, which the template does not declare (tests/test_repair2.py asserts it is not cumulative).
  `test_specs_parts_table_matches_the_template` checks it.

Tests beyond the three named: `test_the_template_has_fixes_hold_and_check_finds_it_served` (definition 2),
`test_specs_parts_table_matches_the_template` (definition 3),
`test_an_auxiliary_counts_moves_over_its_window_and_refuses_over_alone` (the engine change).
tests/test_repair2.py skips every test in this container (no bwrap), so it was not run here.
