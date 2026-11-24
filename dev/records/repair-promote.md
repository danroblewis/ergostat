# repair-promote: with `promote: true`, a block's apply-fix answerer moves down one rung once its record earns it, and back to the owner's rung on a bad fix
depends-on: [repair-lower-rungs]

## Definition of done
`use: repair` takes `promote:`, which is false by default. When it is false, nothing changes.
- **How a block moves down:**
  - The approver a fix gets is worked out from the record each time a fix is tested. It is never stored.
  - It starts at the owner's `approver` and moves down one rung at a time: person → ai → program (only when `approve-with` is set; otherwise skipped) → rule.
  - A block moves down a rung when its last 10 answered fixes at the current rung, ordered by `seq`, were all approved and ran, and none of their failures reached `regressed` or `reverted`.
- **How a block moves back:**
  - Any `regressed` or `reverted` failure of the block, or a person's denial, sends the block back to the owner's rung. Only answers after that point count toward a new promotion.
  - A rung that fails to answer (escalated or held) holds the fix for the person, as now.
- **Edge cases:**
  - Promotion never goes below the rule rung, and never goes above the owner's rung.
  - An unreadable record means the owner's rung.
- **What the record shows:** the `reviewed` approval record says the rung used and the seqs that earned it, so the promotion can be seen on the failure's page.
- **The lock:** the rung is worked out again under the failure's lock before the approval is written. If the block's newest answered seq has moved, nothing is approved and the fix is held.
- **Docs:** SPEC §12r and the template describe `promote`. GAPS drops "promoting a class automatically".

## Relation to other work
- repair-lower-rungs: waits for it; it supplies the program and rule rungs.

## Files to touch
- `ergostat/repair/promote.py` (new)
- `ergostat/repair/fix.py`
- `ergostat/repair/approve.py`
- `ergostat/library/templates/repair/template.yaml`
- `tests/test_repair_promote.py` (new)
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-2: the "last 10" and "after the bad fix" must be ordered by seq, never by `at`.
- lesson-5: the rung is derived, not stored, so an old promotion cannot survive a regression. A failure made again under the same id after a regression must not count its earlier answers.
- lesson-3: an unreadable record must give the owner's rung, never a lower one.

## Acceptance tests
- `tests/test_repair_promote.py::test_off_by_default`: with 10 clean answers and `promote` unset, the person still answers.
- `tests/test_repair_promote.py::test_ten_clean_moves_one_rung`: person → ai after 10 clean answers, and not after 9. The step to program is skipped when there is no `approve-with`.
- `tests/test_repair_promote.py::test_regressed_resets_to_owner_rung`: one regressed fix sends the block back to person; only answers after its seq count again. Timestamps are shuffled so that ordering by `at` would fail.
- `tests/test_repair_promote.py::test_denial_in_the_gap_holds`: a person's denial written between working out the rung and the approval leaves the fix held.
- `tests/test_repair_promote.py::test_unreadable_record_owner_rung`: when the record raises, the owner's rung answers.

## Size budget
130 net lines
size: M (confidence: medium)
