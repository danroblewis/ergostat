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

## Where it stopped
Built, round 1: 127 net lines outside tests, docs and dev (159 added, 32 removed). Every acceptance test exists
and passes. No question could be asked, so these choices were made, each the most reversible one:
- **Three files outside "Files to touch".** `library/templates.py` and `library/expand.py` (3 lines): a parameter's
  `required:` may also be a condition on the parameters above it (`required: "${approver} == program"`). No template
  could otherwise be required to refuse `approve-with` at check time; `required: true` behaves as before (SPEC §2a
  says so). `inbox/stats.py` (2 lines): `program approver (...)` and `rule approver` are counted as an agent's
  answers, as `ai approver (...)` already was. Without that, the rungs' own approvals would count as a person's and
  become evidence for promoting `apply-fix` to `gate: auto`. `test_rung_answers_counted_apart` pins it and fails
  without the change.
- **NAME in `program approver (NAME)`** is the first word of `approve-with` (shlex-split), so the record does not
  carry the command's arguments.
- **"answered"** means the action's first `approved` or `denied`, and the 10 are ordered by that event's seq. An
  action that was approved but has not yet `ran` counts as answered and not clean, so it holds the fix.
- **"the seq of the block's newest answered fix"** is the newest seq of any `approved`, `denied`, `ran` or `failed`
  event on the block's `apply-fix` actions. Under the lock the rule is read again in full, and it approves only if the
  same 10 earn it and that seq is the same. This is stricter than the definition asks: a run landing in the gap also
  holds the fix for the person.
- **"reached regressed or reverted"** means ever, in the failure's history, even under an earlier fix of the same
  failure id (lesson-5: a remade failure keeps its id). This is the stricter reading.
- **The program's environment** is the sandbox's `KEEP` allowlist plus `PATH`. Its cwd is the model's folder, its
  stderr is dropped, and output over 64 KB counts as unreadable. Its timeout is `min(60 s, the loop's timeout)`.
- Not run here: the sandbox-backed tests (31 in `test_repair2.py`, one end-to-end in `test_repair_approver.py`).
  They skipped because bwrap cannot make namespaces in this container, which is the same on main. The unit suite and
  the four browser files were not run (no page changed), as the factory's instructions say.
