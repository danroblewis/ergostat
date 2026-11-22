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
