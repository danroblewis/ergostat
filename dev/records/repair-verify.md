# repair-verify: an applied fix is verified by the runs of its block begun after it, and a fix that regressed offers its revert as a gated action
depends-on: []

## Definition of done

Built on what `main` already has: SPEC §12r, `ergostat/repair/{__init__,apply,capture,fix}.py` and `ergostat/library/templates/repair/template.yaml`. Today an applied fix stays `applied`, and capture reopens a failure that comes back after `applied`. Nothing checks whether the fix worked and nothing can undo it. When this branch is done, the following is true.

**States.** `ergostat.failure` gains three states, `verified`, `regressed` and `reverted`, moved by the events `ergostat.failure.verified`, `.regressed` and `.reverted`. `ergostat.failure.revert-failed` is in neither `STATES` nor `MOVES`. It is a data-only event: it writes the failure's `revert` field and moves nothing. The `on` map is applied from any state, so a `revert-failed` can never fold a `reverted` failure back to `regressed`. `revert` is the only writer of `revert-failed`, and it writes one only when it has just re-read the failure inside the lock and found it `regressed`.

**Verification (in `repair-settle`).** The template gets a new parameter `verify` (integer, default 3). It is the number of runs of the failing block that must finish well before an applied fix counts as verified. Each pass, `settle` handles every `applied` failure on its own, holding `<state>/repair/locks/<name>.lock` through these steps:
1. It takes `fcntl.flock`, the same lock helper `revert` uses.
2. It re-reads the failure. If the failure is no longer `applied`, it writes nothing.
3. It finds the `seq` of the newest `ergostat.failure.applied` event about the failure.
4. It reads the block's `agent.started` events with `after_seq` equal to that seq, oldest first by `seq`. Wall time is never compared (lesson-2). For each run it finds the end event by `causedby` (`agent.ran` or `agent.failed`).
5. It walks those runs in `seq` order:
   - A run with no end event yet stops the walk. Nothing is counted past an unfinished run.
   - An `agent.failed` whose note does not begin with one of capture's `NOT_THE_CODE` endings (timeout, kill, signal, could not start) means **regressed**.
   - An `agent.failed` that does begin with a `NOT_THE_CODE` ending is skipped. It counts neither way.
   - An `agent.ran` adds one good run. When the count reaches `verify`, the fix is **verified**.

The `verified` or `regressed` event writes the failure's `verdict` field: `{runs: [run ids counted], after_seq, verify: {used, asked, clamped}}`, plus the run that regressed and its note when it regressed. The `regressed` event also writes `revert_key = "<name>-<commit>"`.

If an input is missing, the fix is not verified. The failure stays `applied` and `settle` prints why. This covers a failure with no `applied` event found, a block no longer in the model, and an unreadable `commit` (lesson-3).

The docs claim only "`verify` runs begun after it finished well". They never claim the failure is fixed.

**`verify` is bounded at check time and again at run time (lesson-4).** `VERIFY_MAX = 50` and `VERIFY_MIN = 1` live in `ergostat/repair/__init__.py`.
- **Check time.** `check` (`spec/compile.py`, beside the `approver: ai` refusal) refuses a `--verify` in `repair-settle`'s `run` that is not an integer from 1 to 50.
- **Run time.** `settle --verify N` clamps again. Below 1 becomes 1, above 50 becomes 50, and a value that cannot be parsed counts as 50 (the most cautious). `verdict.verify` records `{used, asked, clamped: true}`. The model is never treated as unbounded.
- **What gets read is bounded.** The run query reads at most `10 × verify` `agent.started` events after the seq, so at most 500.

**Asking for the revert.** In the same locked section as the `regressed` event, and on every later pass for a failure already `regressed`, `settle` asks for the gated action `revert-fix`. It calls `gate.request(..., asker="program", key=revert_key)` only if `actions.about(p, fid)` holds no action with that key. A crash between the two writes is therefore repaired on the next pass, and the action is never asked for twice.
- A denied `revert-fix` leaves the failure `regressed`, left to the person. Nothing reopens it.
- A failure the same block raises again while it is `applied` is counted on the item but **not** reopened. Capture opens only from `noted` or `verified`, and `settle` judges the regression.
- A failure that comes back after `verified` is reopened, as an applied one is reopened today.
- A `reverted` failure is not reopened. A person looks at it.

**The revert action.** The template's `revert-fix` action:
- `run: ${python} -m ergostat.repair revert`
- `gate: ${approve}`
- `in: .`
- `timeout: 5m`
- its description says what approving does.

The inbox entry for `revert-fix` carries its own sentence, `REVERTS` in `inbox/entries.py`: "Approving reverts the applied fix COMMIT in your repository with one new commit (git revert); the program goes back to what it was before the fix." The entry does not carry `MERGES`. `MERGES` stays on `apply-fix` only.

**`python -m ergostat.repair revert`.** Steps 1 to 6 all run while holding `<state>/repair/locks/<name>.lock`. The lock is taken before the failure is read and released after its event is written (lesson-1). `name` comes from `fix.ID`'s regex, so the path is built only from a validated name (lesson-11). Inside the lock:

1. It re-reads the failure.
   - If it is `reverted`, it prints "already reverted", writes nothing and exits 0. A retried or repeated run makes no second commit.
   - If it is any state other than `regressed`, it prints why, writes nothing and exits 1.
2. The approved action's `key` must equal the failure's `revert_key`. An old cycle's approval cannot revert a new fix (lesson-5).
3. The failure's `commit` must be 40 hex characters and an ancestor of the owner's `HEAD` (`merge-base --is-ancestor`).
4. The owner's tree must be clean (`status --porcelain --untracked-files=no` is empty). No `REVERT_HEAD`, `MERGE_HEAD`, `CHERRY_PICK_HEAD` or `sequencer` may exist (`rev-parse --git-path`). A failed check is recorded as `revert-failed` with why.
5. It records `head0`, then runs `git revert --no-edit <commit>` through `sandbox.git` (hooks, editor and filters off, identity `ergostat`, `-c gc.auto=0`).
6. If git fails (`CalledProcessError`) or times out (`subprocess.TimeoutExpired`, from `_git`'s 120 s), it runs `git revert --abort`. It then checks that `REVERT_HEAD` is gone, `HEAD == head0`, and `status` is clean. It records `revert-failed` with `{why, aborted: true|false}`. If the abort did not restore everything, `why` tells the owner the repository is left mid-revert. It exits 1, and the failure stays `regressed`. On success it records `reverted` with `{revert_commit, of: commit}`.

**What stops a hung revert (lesson-6).**
- **Each git call is bounded.** `sandbox.git._git` runs every git call with `timeout=120`. On timeout, `subprocess.run` kills git. Hooks are off and `gc.auto=0`, so git starts no children of its own.
- **The action timeout is above that.** The action's `timeout: 5m` is above one git call plus the abort.
- **The whole session is killed if the action's timeout passes anyway.** `actions/gate.py:run_once` already starts the command with `start_new_session=True`. On `TimeoutExpired` it now kills the whole session with `os.killpg(pid, SIGKILL)`, so the shell, `python -m ergostat.repair revert` and its git all stop. Today only `sh` is killed.
- **The lock cannot outlive the process.** The lock is an `fcntl.flock` on an open file descriptor, and the kernel releases it when the process dies. A killed revert cannot hold it.
- **A revert killed mid-way leaves no unnoticed state.** If it leaves a `REVERT_HEAD`, the next `revert` refuses at step 4 with `revert-failed` ("a revert is in progress in your repository"). It never runs `--abort` on a revert it did not start in that same call.

**Same id, made again (lesson-5).** Capture's `opened` event, from `noted` or `verified`, writes `verdict: null`, `revert: null` and `revert_key: null`. The fields of an earlier cycle are cleared that way. Verification always counts from the **newest** `applied` event's seq, so runs before a re-apply never count toward it.

**Template.** The template gets:
- the parameter `verify`;
- the action `revert-fix`;
- `repair-settle`'s `run` with `--verify ${verify}`, and its `out` with the new flows;
- `applied-fixes` turned into a plain stock: fixes applied and being verified (state `applied`), no longer cumulative;
- a stock `regressed-fixes` (state `regressed`);
- flows `fixes-verified` (out of `applied-fixes`), `fixes-regressed` (from `applied-fixes` to `regressed-fixes`) and `fixes-reverted` (out of `regressed-fixes`);
- its `reading` updated.

**Docs.** SPEC §12r covers the states, verification, the revert, the parameter and its bounds, and the table, and its "does not do yet" sentence is updated. The agent guide's §3i and GAPS' Repair entry (*Left*) say that verification and the revert are done.

## Files to touch

- `ergostat/repair/__init__.py`: the states, the moves, `VERIFY_MIN` and `VERIFY_MAX`
- `ergostat/repair/apply.py`: `settle`'s verification and revert request, `revert()`, the shared `locked(p, name)` helper, `main`'s `revert` and `settle --verify`
- `ergostat/repair/capture.py`: opens only from `noted` or `verified`, clears the cycle's fields, keeps `began`
- `ergostat/spec/compile.py`: the check-time bound on `--verify`
- `ergostat/actions/gate.py`: `run_once` kills the process group on timeout
- `ergostat/inbox/entries.py`: the `REVERTS` sentence for `revert-fix`
- `ergostat/library/templates/repair/template.yaml`
- `tests/test_repair_verify.py` (new, reusing `tests/test_repair2.py`'s `project`, `broken`, `fixed` and `git` helpers)
- `docs/SPEC.md` §12r, `docs/AGENT-GUIDE.md` §3i, `docs/GAPS.md` (Repair), `docs/roadmap/overnight/repair-verify.md`

## Risks

- **lesson-1.** There are three read-decide-write paths.
  - `revert` reads `regressed` and the key, runs git, then writes `reverted` or `revert-failed`. It holds the per-failure lock from before the read until after the write and re-reads inside it.
  - `settle` reads `applied`, judges the runs, then writes `verified` or `regressed` and asks for the action. Same lock, re-read inside it.
  - `revert-failed` is data only, so no fold move can undo a `reverted`.

  Without the lock, a second revert run (a retry, or a rerun after a timeout) refuses and folds a `reverted` failure back. Tests: `test_l1_an_approved_revert_run_twice_makes_one_revert_commit_and_stays_reverted`, `test_l1_two_reverts_at_once_make_one_commit`, `test_l1_settle_rereads_inside_the_lock`.
- **lesson-2.** "Runs after the fix" could be judged by `time >= applied.time`. Order by `seq`. Test: `test_l2_runs_are_counted_after_the_applied_event_by_seq_not_time`.
- **lesson-3.** Missing inputs could fail open: no `applied` event, a block gone, a run with no end event, an unparseable `verify`. Each must mean not verified, or the most cautious bound. Test: `test_l3_a_failure_whose_runs_cannot_be_read_is_not_verified`.
- **lesson-4.** `verify` multiplies the runs read. It is bounded to 1–50 by `check`, and clamped again in `settle` with the clamp written into the failure's fields. Tests: `test_l4_check_refuses_verify_out_of_range`, `test_l4_settle_clamps_verify_from_a_compiled_model_that_bypassed_check`.
- **lesson-5.** A failure verified, reopened and fixed again keeps its old `verdict`, `revert` or `revert_key`, or counts runs from the first apply. An old cycle's approved `revert-fix` reverts a new fix. Tests: `test_l5_a_reopened_failure_clears_its_verdict_and_counts_from_the_newest_apply`, `test_l5_an_old_cycles_revert_approval_cannot_revert_a_new_fix`.
- **lesson-6.** A conflicting or hung `git revert` could leave a half-done revert, keep the lock, or keep running after the action's timeout. Covered by the abort with its post-checks, `_git`'s 120 s, `killpg` in `run_once`, and the kernel-released flock. Tests: `test_l6_a_conflicting_revert_is_aborted_leaves_nothing_half_done_and_stays_regressed`, `test_l6_a_revert_whose_git_times_out_is_aborted_and_frees_the_lock`, `test_l6_an_action_past_its_timeout_has_its_whole_process_group_killed`.
- **lesson-7.** Merge origin/main and run the suites again. `gate.py` and `entries.py` are shared with other branches.
- **lesson-8.** Two claims must stay narrow:
  - "verified" means `verify` runs begun after the fix finished well. It does not mean the failure is fixed.
  - "the revert changes nothing else" is shown by a test that compares trees.

  The inbox sentence must not say "merges" for a revert. Tests: `test_the_revert_restores_the_programs_text_and_changes_nothing_else`, `test_the_inbox_says_what_approving_a_revert_does`.
- **lesson-9.** Every test above is first run against the code with the guarded line broken, and the implementor reports that it failed. The guarded lines are: the lock removed, the `seq` filter turned into a time filter, the clamp removed, the clearing removed, the `--abort` removed, and `killpg` turned back into a kill of only the shell.
- **lesson-10.** The concurrency tests synchronise on events or the lock file, never on fixed sleeps. The process-group test polls for the child's pid to be gone, with a deadline.
- **lesson-11.** The lock path is built from a name that matched `fix.ID`. The revert target must be 40 hex and an ancestor of `HEAD`. Nothing is deleted.
- **lesson-12.** No earlier review findings on this branch. The three plan-review points are answered above.
- **lesson-13.** A suite failure outside these files is reported, not fixed.

## Acceptance tests

All in `tests/test_repair_verify.py`.

- `test_a_fix_is_verified_after_verify_good_runs_begun_after_it`: an applied fix, then 3 good runs of the collector, and `settle` moves the failure to `verified`, with `verdict.runs` listing those 3 run ids. After 2 runs it is still `applied`.
- `test_a_failed_run_after_the_fix_regresses_it_and_asks_for_revert_fix_once`: after apply, the collector fails again. Capture counts it without reopening, `settle` moves the failure to `regressed`, and exactly one `revert-fix` exists with key `<name>-<commit>`. A second `settle` asks nothing more.
- `test_a_run_ended_by_timeout_or_kill_counts_neither_way`: a run ended by timeout or kill is neither a good run nor a regression.
- `test_settle_asks_the_revert_again_when_it_was_lost`: the `regressed` event is written but the action request is skipped (monkeypatched to raise once). The next `settle` asks for the action.
- `test_the_approved_revert_reverts_with_one_commit`: after the approval, `revert` makes one revert commit on the owner's branch, the failure is `reverted`, and `revert_commit` is recorded.
- `test_the_revert_restores_the_programs_text_and_changes_nothing_else`: after the revert, the owner's tree equals the tree before the fix was applied. Every tracked file is compared.
- `test_the_inbox_says_what_approving_a_revert_does`: the `revert-fix` entry's `warn` is `REVERTS` and contains no "merges". The `apply-fix` entry still carries `MERGES`.
- `test_l1_an_approved_revert_run_twice_makes_one_revert_commit_and_stays_reverted`: `revert` runs twice with the same approved action. There is one revert commit, the state is `reverted`, there is no `revert-failed` event, and the second run exits 0.
- `test_l1_two_reverts_at_once_make_one_commit`: the test holds the lock file, starts two `revert`s in threads, then releases. There is one revert commit and one `reverted` event.
- `test_l1_settle_rereads_inside_the_lock`: a monkeypatched step between `settle`'s listing and its lock writes a newer `applied` for the failure, from a reopened cycle. `settle` counts from the newer seq and writes no `verified` built from the older runs.
- `test_l2_runs_are_counted_after_the_applied_event_by_seq_not_time`: runs are recorded with a monkeypatched clock. A run whose `time` is equal to or earlier than the `applied` event's, but whose `seq` is later, is counted. One whose `time` is later but whose `seq` is earlier is not.
- `test_l3_a_failure_whose_runs_cannot_be_read_is_not_verified`: three cases each leave the failure `applied` with nothing written: no `applied` event (stripped), the block removed from the compiled model, and a run with no end event before the good runs.
- `test_l4_check_refuses_verify_out_of_range`: `verify: 0`, `51` and `x` are refused by `check`. `1` and `50` are accepted.
- `test_l4_settle_clamps_verify_from_a_compiled_model_that_bypassed_check`: the compiled spec's `repair-settle` `run` is patched to `--verify 5000`, and the engine runs the block. After 3 good runs the failure is not verified. After 50 it is `verified`, with `verdict.verify == {used: 50, asked: "5000", clamped: true}`. Also `--verify -3` gives `used: 1, clamped: true`.
- `test_l5_a_reopened_failure_clears_its_verdict_and_counts_from_the_newest_apply`: a failure is verified, then fails again and is reopened. `verdict`, `revert` and `revert_key` are null. It is fixed and applied again, and the good runs from the first cycle do not count.
- `test_l5_an_old_cycles_revert_approval_cannot_revert_a_new_fix`: a `revert-fix` approved for an earlier commit is refused. There is no git change and no state change.
- `test_l6_a_conflicting_revert_is_aborted_leaves_nothing_half_done_and_stays_regressed`: the owner commits a change to the same lines after the fix, then approves the revert. `revert --abort` ran, there is no `REVERT_HEAD`, `HEAD` and the tree are unchanged, `revert-failed` is recorded with `aborted: true`, and the failure is `regressed`.
- `test_l6_a_revert_whose_git_times_out_is_aborted_and_frees_the_lock`: `sandbox.git._git` is monkeypatched to raise `TimeoutExpired` on `revert`. The abort runs, `revert-failed` is recorded, the failure stays `regressed`, and the lock can be taken at once afterwards.
- `test_l6_an_action_past_its_timeout_has_its_whole_process_group_killed`: an approved action with a 1 s timeout whose command forks a grandchild that sleeps and writes its pid. After `run_once`, the action is `failed` with "stopped after its timeout", and the grandchild's pid is gone, polled with a deadline.
- `test_a_dirty_tree_or_a_revert_in_progress_is_refused_not_touched`: the owner has a staged change, or a `REVERT_HEAD`. `revert-failed` is recorded with why, and the owner's files and `HEAD` are byte-for-byte unchanged.

The existing `tests/test_repair2.py` must still pass. `test_use_repair_is_a_system_in_all_three_views` is changed only where `applied-fixes` is no longer cumulative, and it also asserts that `regressed-fixes` is in the system.

## Size budget

280 net lines outside `tests/` and `docs/`, the template's YAML counted. The estimate is about 110 in `apply.py`, 10 in `__init__.py`, 8 in `capture.py`, 10 in `compile.py`, 10 in `gate.py`, 6 in `entries.py` and 30 in the template. The rest is margin for the abort's post-checks.

## Notes from the plan review (answer each)

- A revert whose git commit succeeded but whose `reverted` event was never written (a 5m killpg or a crash in that window) leaves the failure `regressed` with the repository already reverted. A retry would conflict and record a false `revert-failed`. Inside the lock, before running git, look for an existing commit between head0 and `commit` that reverts `commit`; if one exists, record `reverted` with it and test this case. Until then, narrow the claim 'a retried run makes no second commit' to the case where `reverted` was written.
- Define `aborted: true` as 'the post-checks passed' (no REVERT_HEAD, HEAD == head0, clean tree), not 'git revert --abort exited 0'. In the timeout test the patched _git starts no revert, so the abort itself fails. Assert that meaning in both l6 tests.
- A `regressed` failure whose revert-fix was denied can never leave `regressed`: capture won't reopen it and nothing else moves it. Document how a person moves it on, or state in SPEC that it stays regressed.
- Verification can stall for good: a run with no end event, or a first 10×verify window of only NOT_THE_CODE endings, keeps the failure `applied`. That fails closed, which is right, but settle must print why it can't decide and SPEC must say this can happen.
- Any non-infra agent.failed of the block counts as a regression, even one from a different failure. Record the regressing run's failure id in `verdict` and whether it matches this failure, and keep the SPEC wording to what is actually judged.
- test_l1_an_approved_revert_run_twice passes with the lock removed (the second run re-reads `reverted`), so only the threaded test guards the lock. Say which test failed for each guarded line in the lesson-9 report. Also add a case to test_l1_settle_rereads_inside_the_lock where the competing write moves the failure out of `applied`, and assert that settle writes nothing.

## Where it stopped

Built, round 1: everything in the definition above, with the acceptance tests in `tests/test_repair_verify.py` (24
with the parametrised cases). The size is 250 net lines outside `tests/`, `docs/` and `dev/` (budget 280).

**The plan review's points, answered.**
- A revert whose git commit was made but whose `reverted` event was never written: before running git, `revert` looks
  for a commit in `commit..HEAD` whose message says `This reverts commit <commit>.`, and if it finds one it records
  `reverted` with it (`found: true`) and makes no commit. Test: `test_a_revert_whose_event_was_lost_is_found_not_made_again`.
- `aborted: true` means the post-checks passed (no `REVERT_HEAD` or other pending state, `HEAD == head0`, a clean
  tree), whatever the abort's exit code. Both l6 tests assert it. In the timeout test the abort itself fails, since no
  revert was started.
- A denied `revert-fix` leaves the failure `regressed` for good. SPEC §12r says so, and says a person reverts or
  fixes it by hand.
- A stall (a run that never ends, or more than 10 × verify runs since the fix with none deciding it) keeps the failure
  `applied`. `settle` prints why on each pass, and SPEC says this can happen.
- The `regressed` verdict records `run`, `note`, `failure` (this failure's id when triage recorded that run on it,
  else null) and `same`. SPEC only says that a failed run of the block regresses the fix.
- The lesson-9 report is below. `test_l1_settle_rereads_inside_the_lock` has the `moved-out` case.

**Lesson-9: each guarded line broken, and the test that failed.**
- Lock removed (`locked` takes no flock): `test_l1_two_reverts_at_once_make_one_commit` failed. As the review said,
  `..._run_twice_...` and `test_l1_settle_rereads_inside_the_lock` still passed.
- Re-read removed in `settle` (the `state != "applied"` check gone): `test_l1_settle_rereads_inside_the_lock[moved-out]`
  failed. `[applied-again]` still passed, because the newest-`applied` query is also inside the lock.
- `seq` filter turned into `since=applied.time`: `test_l2_runs_are_counted_after_the_applied_event_by_seq_not_time`
  failed.
- Clamp removed: `test_l4_settle_clamps_verify_from_a_compiled_model_that_bypassed_check` failed.
- Clearing removed (capture's `opened` without the nulls):
  `test_l5_a_reopened_failure_clears_its_verdict_and_counts_from_the_newest_apply` failed.
- `--abort` removed: both `test_l6_a_conflicting_revert_...` and `test_l6_a_revert_whose_git_times_out_...` failed.
- `killpg` turned back into `r.kill()`: `test_l6_an_action_past_its_timeout_...` failed. It first passed under the
  break, because the middle process held the output pipes until its sleeping child ended. The test's middle process now
  points its output at /dev/null, and the test asserts that `run_once` returns within 30 s.

**Choices made with nobody to ask (the most reversible taken).**
- The run query takes the newest `10 × verify` `agent.started` after the seq (`query(n=...)`). This is all of them
  when there are fewer. When it is full and an older one exists (one more event read), the fix is not verified and
  settle says why. The store has no oldest-first limit, and adding one was outside the gap.
- `revert` steps 1 and 2 (wrong state, or a key that is not the failure's `revert_key`) print and write nothing. This
  way an old cycle's approval leaves no `revert-failed` on the new cycle. Steps 3 and 4 record `revert-failed`.
- `REVERTS` is written with `{commit}`, filled with the commit's first 12 characters. `entries.warning()` picks
  `REVERTS` for `revert-fix` and `MERGES` for any other action about a failure. A `revert-fix` entry's `why` is the
  same sentence, never the `MERGES` text.
- `repair-settle` lists `actions: [revert-fix]`, since it is the block that asks for it.
- Capture keeps `began` for a new failure and for one reopened from `verified`. Otherwise it drops it, as before.
- The tests run without the OS sandbox: the collector is `read-only: false` and there is no `test:`, so the fix goes
  untested to its approval. The l2 test sets times with `events.add(at=...)` rather than a monkeypatched clock.
- `tests/test_inbox.py::test_a_delivery_passes_through_its_gate_...` patched `gate.subprocess.run`, which `run_once`
  no longer calls. Its patch now targets `gate.subprocess.Popen`. The change is one line, and it is caused by this
  gap's `gate.py`.

**Not run here.**
- `tests/test_repair2.py` is skipped whole in this container: "bwrap cannot make its namespaces here". That includes
  the edited `test_use_repair_is_a_system_in_all_three_views`. It needs a host or `scripts/in_container.sh --sandbox`.
- The full unit suite and the four browser files were not run (they are left for the factory's runs, as instructed).
- The clone has no `origin` remote. Local `main` (e1e778c1) is this branch's base, so there was nothing to merge.

Run, one file at a time: `tests/test_repair_verify.py` (24 passed), `tests/test_inbox.py` (30 passed). Also, together:
`test_act_risk`, `test_gated_actions`, `test_modelreview`, `test_program_actions`, `test_recipes`, `test_resilience`,
`test_runlog`, `test_triggers2`, `test_sandbox_attacks`, `test_repair2_live`, `test_redesign_bench`, `test_impact` and
`test_calls`, all passing (the sandbox ones skipped). `ruff check ergostat tests scripts` is clean.

### Round 2

**The finding answered (the only one, blocking).** `judge()` took the newest `10 × verify` `agent.started` after the
applied seq and gave up when an older one existed. A block that ran faster than settle's passes would leave its failure
`applied` for good. Now:
- The event store has an oldest-first limit. `query(first=k)` returns the oldest `k` matching events, by seq. It is
  in both backends: `store.Events` uses `order by seq limit k`, and `segments.Segments` passes it to `_scan`'s existing
  `limit`, whose segment walk now stops reading rows once it has `k`. This is a new keyword. No caller's behaviour
  changes, but `store.py` and `segments.py` are shared files (lesson-7). I chose it over paging with `before_seq` and
  `after_seq` because it is one bounded read, and because it is the most reversible fix: one keyword, used in one place.
- `judge()` reads `query(first=10 × verify, after_seq=<applied seq>)` and walks those runs oldest first. The first
  decisive run decides, however many runs began after it. The "more than N runs" bail-out is gone. When the whole
  window of `10 × verify` runs ended by timeout, kill, signal or failing to start, settle says "the first N runs begun
  since the fix decided nothing" and the failure stays `applied`. This is the stall the plan review named. It fails
  closed.
- SPEC §12r now says this: it reads the oldest ten times `verify` runs, so a failed first run regresses the fix however
  many followed. The stall sentence names only the all-timeouts-or-kills window. The ends query is unchanged. It is
  still read by `causedby` from the first counted run's seq on. That read is item-indexed, but it is not capped.
- New tests:
  - `test_a_failed_first_run_regresses_the_fix_however_many_runs_follow_it`: the first run fails, then 40 good runs,
    more than 30.
  - `test_three_good_first_runs_verify_the_fix_however_many_runs_follow_them`: 3 good runs, then 40 failed ones.
  - `test_a_first_window_of_only_timeouts_is_not_verified_and_says_why`
  - `test_the_store_reads_the_oldest_first_events[sqlite|segments]`: the segments case asserts that it reads across
    sealed segments and the head.
- Lesson-9:
  - Turning `first=limit` back into `n=limit`, the newest window, failed all three settle tests.
  - Making `Segments.query` ignore `first` failed `test_the_store_reads_the_oldest_first_events[segments]`.
- The size is about 259 net lines outside `tests/`, `docs/` and `dev/`, inside the budget of 280.

**Run this round, one file at a time:**
- `tests/test_repair_verify.py`: 29 passed.
- `tests/test_inbox.py`: 30 passed.
- `tests/test_storage.py`: 7 passed.
- `tests/test_rollup.py`: 48 passed.
- `tests/test_item_index.py`: 55 passed.
- `tests/test_repair2.py`: 32 skipped, because bwrap cannot run in this container, as in round 1.

`ruff check ergostat tests scripts` is clean. Local `main` (e5d8c220) is already merged into the branch (55b4de67).
There is no `origin` remote, so nothing newer could be merged. The full unit suite and the four browser files are
left for the factory's runs.
