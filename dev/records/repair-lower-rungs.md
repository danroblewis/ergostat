# repair-lower-rungs: `approver: program` and `approver: rule`, the ladder's lower rungs for apply-fix
depends-on: []

## Definition of done
In a model with `use: repair` (SPEC §12r), `approver:` also takes `program` and `rule`. Neither ever calls an AI.
- **Both rungs need the guard to pass first.** The fix's test passed and `allow.escalate` gives no reason. Otherwise the fix is held for the person, as now.
- **`approver: program`:**
  - The template takes `approve-with:`, a command of the owner's project. It is required when the approver is `program`; without it the template refuses at check time.
  - The command is given on stdin exactly what the AI approver is given: the program's path, the diff made from the texts the guard judged, and "passed". It runs with no secrets in its environment and a timeout of at most 60 s. On a timeout its whole process group is killed.
  - The fix is approved only when the command exits 0 and its stdout is JSON with `"approve": true`. Anything else holds the fix for the person: another exit code, a timeout, a failure to start, or unreadable output.
- **`approver: rule`:**
  - The rule approves only when the fix's block has earned it. Look at the last 10 `apply-fix` actions answered for failures of that block, ordered by `seq`. All 10 must have been approved and run, and none of their failures may have reached `regressed` or `reverted`.
  - The fix is held when the block has fewer than 10 answered fixes, when any of them was denied, or when the record cannot be read.
  - The approval record carries the seqs of the 10 actions that earned it.
- **One recording path for both rungs:**
  - Each answer is recorded as `reviewed` through the same path as the AI's. It uses the same stamp, and the approval is written only after `current` is re-checked under the failure's lock. Its `by` is `program approver (NAME)` or `rule approver`. The approval sets `approved_by` to the same.
  - For the rule rung, that re-check also checks that the seq of the block's newest answered fix is unchanged.
  - A person's denial stays final.
- **Docs:**
  - SPEC §12r states the two rungs and their limits: the rung's judgement is only as good as the guard and the owner's program.
  - The agent guide gets one sentence on them.
  - The template's `approver` choices list both.
  - `docs/GAPS.md`'s Repair *Left* drops "the ladder's lower rungs (program, rule)".

## Relation to other work
- repair-promote: builds on this; it picks among these rungs.
- repair-log-events, repair-traces-more: avoid these files.

## Files to touch
- `ergostat/repair/approve.py`
- `ergostat/repair/fix.py`
- `ergostat/library/templates/repair/template.yaml`
- `tests/test_repair_rungs.py` (new)
- `docs/SPEC.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`

## Risks
- lesson-1: the rule reads the block's record, decides and then approves, so a denial landing in between could be missed. The decision is checked again under the lock before the approval is written.
- lesson-3: a crashed, timed-out or silent program, or an unreadable record, must never approve. Each of these holds the fix.
- lesson-6: a hung approver program must be killed together with its children.

## Acceptance tests
- `tests/test_repair_rungs.py::test_program_approves_only_on_exit_0_and_true`: exit 1, bad JSON and `"approve": "yes"` each leave the fix held; only exit 0 with `true` approves it, and the approval records `program approver`.
- `tests/test_repair_rungs.py::test_program_timeout_kills_group_and_holds`: an approver that starts a child and sleeps is killed with its child, and the fix stays held.
- `tests/test_repair_rungs.py::test_guard_reason_never_reaches_program_or_rule`: a fix the guard escalates is held, and the program is never run.
- `tests/test_repair_rungs.py::test_rule_needs_ten_clean_answers_by_seq`: with 9 approved fixes, or 10 with one regressed, the fix is held; with 10 clean ones it is approved. The record's timestamps are shuffled so that ordering by `at` would give a different answer.
- `tests/test_repair_rungs.py::test_rule_denial_in_the_gap_wins`: a denial written between the rule's read and its write (monkeypatched) means nothing is approved.
- `tests/test_repair_rungs.py::test_rule_unreadable_record_holds`: when the record raises, the fix is held.

## Size budget
220 net lines
size: L (confidence: low)
