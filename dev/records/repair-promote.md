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

## Where it stopped
Built, round 1: 98 net lines outside tests, docs and dev (`promote.py` 87, `approve.py` +3, `fix.py` +6, the
template +2). Every acceptance test exists and passes (9 runs with the parametrized cases, plus
`test_a_denial_resets_too`). Each was seen to fail with the code it guards broken: the lock's re-check dropped
(`test_denial_in_the_gap_holds[another-fix]`), the reset cut ignored (`test_regressed_resets_to_owner_rung`), an
unreadable record read as the rule (`test_unreadable_record_owner_rung`), promotion always on (`test_off_by_default`),
`EARN` 9 (`test_ten_clean_moves_one_rung[9]`). Nobody could be asked, so these readings were taken, each the stricter
or more reversible one:
- **"answered at the current rung"** is read from the answer's `approved_by` (`ai approver`, `program approver`,
  `rule approver`, else the person). A fix the promoted rung escalated and the person then approved counts toward the
  person's rung only, so it neither resets nor advances the promoted rung.
- **"a person's denial"**: any `denied` of one of the block's `apply-fix` actions resets (only people and the gate's
  own `deny` write one; with `approve: deny` nothing is ever approved anyway).
- **"its last 10 ... at the current rung"**: after each step down the count starts again from the next answer at the
  new rung; an approved fix not yet `ran` (or whose run `failed`) is in the window and not clean, so it holds.
- **A regression or revert** is any `ergostat.failure.regressed` or `.reverted` event about a failure of the block
  (the kind is sealed, so only ergostat writes them), by seq; answers at or before its seq never count again, which is
  also what keeps a failure remade under the same id from counting its earlier answers (lesson-5).
- **"newest answered seq"** is the newest seq of any `approved`, `denied`, `ran` or `failed` of the block's
  `apply-fix` actions and any of its regressions or reverts. Under the lock the rung is worked out again whenever
  `promote` is on (also when the rung is the owner's), and the fix is held if the rung or that seq differs: stricter
  than asked, as the rule's own re-check is.
- **The record**: the `reviewed` approval carries `rung` and `rung_earned` (the 10 seqs of the last step down; null
  at the owner's rung). `rung_earned` is a new key so it never collides with the rule's own `earned`.
- `docs/GAPS.md` is not edited (the queue writes it): "promoting a class automatically" is dropped from the Repair
  umbrella's *Left* in `dev/records/repair.md`, and the gap's line is the `## Entry` below. The agent guide got one
  sentence on `promote`, as the house rules ask, although it is not in "Files to touch".
- Not run here: the sandbox-backed tests (31 in `test_repair2.py`, one in `test_repair_approver.py`) skipped because
  bwrap cannot make namespaces in this container, as on main. The unit suite and the four browser files were not run
  (no page changed), as the factory's instructions say. Run: `test_repair_promote.py`, `test_repair_rungs.py`,
  `test_repair_approver.py`, `test_repair_verify.py`, `test_repair2.py`; ruff clean.

Round 2 (one review finding, blocking; answered): `promote.rung_of` read every `approved_by` that was not an
approver's as the person's rung, so 10 approvals by an agent through the MCP (`owner via mcp`) promoted the block.
Now the person's rung is counted only when `stats.by_person(approved_by)` holds (`owner`, or a login's email); any
other answer (`owner via mcp`, the gate's own `GATE`) counts toward no rung: it is skipped, neither earning nor
breaking a run of 10 (a denial through the MCP still resets, as any denial does). Skipping rather than resetting is
the more reversible reading. SPEC §12r's "else the person" now says this; the template's `promote` description and
the agent guide say an agent's answers never earn a step. New test `test_agent_answers_never_promote`: 10 `owner via
mcp` and 5 gate approvals leave the person answering (the fix stays requested, no review), and the owner's own 10
answers around them still earn the step; it was seen to fail (`'ai' == 'person'`) with the old reading restored.
Net lines outside tests, docs and dev now about 101. Run: `test_repair_promote.py` (10 passed),
`test_repair_rungs.py`, `test_repair_approver.py`, `test_repair_verify.py` (73 passed, 1 skipped for bwrap),
`test_repair2.py` (31 skipped for bwrap, as on main); ruff clean. `main` has nothing the branch lacks. The unit suite
and the browser files were not run here (no page changed).

## Entry

entry-of: repair
done: 2026-11-24 Promotion down the ladder (`repair-promote`, SPEC §12r): with `promote: true` the rung a block's fix is answered at is worked out from the record each time (never stored), from the owner's `approver` down one rung (person, ai, program only with `approve-with`, rule) per 10 clean answers at the rung by seq, and back to the owner's rung on a regressed or reverted fix or a denial; an unreadable record is the owner's rung, the `reviewed` record shows the rung and the seqs that earned it, and the rung is read again under the failure's lock before any approval.
