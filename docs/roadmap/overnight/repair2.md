# repair2: a failing program triaged, fixed by an AI in a disposable clone, and proposed as a gated change

Branch `repair2`, from main (dd91518). The second attempt at the self-repair loop (the owner, 2026-11-19: run failures
are triaged and fixed by AI, with an impact report and an approval ladder; human approval rare, for a system's early
stages). The first, `repair`, was parked after two failed gates (`docs/roadmap/overnight/repair.md`, *Where it
stopped*): **X1**, git ran the fixer's own config outside the sandbox (the fixer could write its worktree's git
metadata, which was the owner's); **X2**, the jail was a deny list (reads everywhere but listed folders; network open
once one host was listed). Since then `ergostat/sandbox/` landed on main (SPEC §12q): a `(deny default)` seatbelt
profile, bwrap with an empty root, a filtering CONNECT proxy, git with owned config, a reaper. This branch adopts it and
lands only what is safe: **triage, the fix proposed as a gated change with an impact report, and the first two rungs of
the approval ladder (a person; then an AI approver with an approval record).** Verification after applying, the revert
offer, per-run log files, log events, the swallowed-errors check and the lower rungs (narrow AI, program, rule) are
left for later.

## Definition of done

**Triage.** In a model with `use: repair`, every failed run of a program or ai block (a non-zero exit) is recorded as
`ergostat.run.failed` about an item of the built-in kind `ergostat.failure`, one item a signature (the block, its
program, the exception's type and innermost frame in the project; without a traceback, the block and how it ended):
its error, traceback, the tail of its standard error (scrubbed of secrets), its program and the input it was given
(kept in the state directory). The same failure again counts on its item. A failure starts `noted`, and is opened for
repair only when its block runs a program of the project's and it did not end by a timeout, a kill or a signal. The
repair loop's own runs, and runs a failure's events caused, record no failure. The kind exists only in a model that
uses repair. **A failure's fields are ergostat's alone**: an event about one whose type is not ergostat's own is
refused by the fold (so no block line, sensor observation, push, `event --add`, MCP call or legacy runner can change
them), and the impact report reads them the same way.

**The fix, in a disposable clone, by allowlist.** `repair-fix` (an `ai` block whose `run:` is ergostat's, haiku by
default) takes each open failure, leased: makes a **clone** of the project's repository (`git clone --no-local
--no-hardlinks`: its own `.git`, never the owner's, never a worktree, no shared objects) at the owner's `HEAD`; gives the
AI (`claude -p` with no tools at all) the failure and **only the files ergostat read for it**: the program and the
plain files beside it (no dot-files, no links, capped, scrubbed); and takes back one answer, the program's new text and
an explanation. ergostat writes it into the clone (refusing any other path, a link, or no change) and commits it with
`ergostat.sandbox.git.Repo`. The **test** runs in `ergostat.sandbox` on a throwaway copy of the clone's files (no `.git`):
reads only the copy and the toolchain; writes only the copy and its temporary folder; a `read-only: true` block is
re-run on the input that failed, its `network:` hosts reachable through the proxy for `GET` and `HEAD` only; any other
block runs the template's `test:` command, or is left untested (said). The test's output is scrubbed. Failed: the
failure is given back (a lease attempt; a dead letter after `tries`). Passed or untested: the **impact report**
(SPEC §12n) is worked out for the failure and kept with it (`impact`, `tests`, `risk`, the report as a file), and the
gated action `apply-fix` is asked for: the fix proposed as a gated change.

**The ladder's first two rungs.** `approver: person` (the default): `apply-fix` is held for the owner, in the inbox and
on the failure's page. `approver: ai`: an AI approver (haiku, no tools) reads the diff, the test and the impact report
and answers approve or escalate, with reasons; ergostat lets it approve only when the tests passed and the risk is not
high; its answer is the **approval record** (`ergostat.failure.reviewed`: who, the model, the verdict, the reasons, the
guard, the cost) and an approval is recorded on the action as `approved_by: "ai approver (MODEL)"`, counted apart from a
person's in the inbox's record; escalated, the action stays held for the person. **Applying** (the approved action) in
the owner's repository: its `HEAD` must still be the commit the fix was made on, the clone's metadata must be what
ergostat made, then the tested commit is fetched and fast-forwarded (`--ff-only`: git refuses atomically if anything
moved or a local change would be overwritten); refused, the failure goes back to open. `repair-settle` dismisses a
failure whose action was denied, and removes clones no failure needs.

**Costs and caps.** Every AI call's Claude Code result is passed on, so the run's cost is recorded as any AI run's;
`budget:` per call (`--max-budget-usd`) and `daily:` across all of them, kept in a ledger under a lock and checked
before each call against what the day spent plus the call's budget: an unreadable ledger, or one over the cap, means no
call (it fails closed).

**Docs.** SPEC §12r (after the sandbox), the agent guide (what `use: repair` does, and failing hard), GAPS.

## Acceptance tests (`tests/test_repair2.py`)

- `test_a_failed_run_is_triaged_into_one_failure_a_signature_and_counted`
- `test_a_timeout_or_a_failure_with_no_program_is_noted_not_opened`
- `test_the_repair_loops_own_runs_record_no_failures`
- `test_m1_a_failures_fields_cannot_be_spoofed_by_any_event_not_ergostats`
- `test_use_repair_is_a_system_in_all_three_views`
- `test_the_loop_fixes_in_a_clone_proposes_with_an_impact_report_and_the_person_approves` (end to end: the engine, a
  stand-in AI, the owner's approval)
- `test_the_ai_approver_approves_with_an_approval_record`
- `test_the_ai_approver_escalates_to_the_person_when_the_guard_or_the_ai_says_so`
- `test_a_fix_that_fails_its_test_is_given_back_and_nothing_is_asked`
- `test_x1_the_clone_has_its_own_git_and_a_repair_cannot_write_the_owners`
- `test_x1_a_proposal_naming_another_file_or_a_link_is_refused`
- `test_x2_the_ai_is_given_only_the_allowlisted_files_and_has_no_tools`
- `test_x2_a_fix_under_test_reads_nothing_outside_its_allowlist_and_its_output_is_scrubbed`
- `test_m2_m3_a_fix_cannot_tell_it_is_under_test_and_leaves_no_process_behind`
- `test_m6_a_read_only_rerun_reaches_its_hosts_for_get_only`
- `test_m7_the_daily_cap_fails_closed_and_never_overshoots`
- `test_m8_apply_refuses_a_moved_head_a_local_change_or_a_tampered_clone`
- `test_seatbelt_profiles_keep_filter_lists_short_and_no_syscall_rules` (the kernel-panic guard, over the profiles a
  repair test builds)

M4 (the fixer's regression test run first, kept in the repository) is designed away: a fix changes only the failing
program, and the AI has no tools to run anything (covered by `test_x1_a_proposal_naming_another_file...`). M5 (the
swallowed-errors check) is not built here. A live check, `tests/test_repair2_live.py` (skipped unless
`ERGOSTAT_LIVE_AI=1`), runs the loop with haiku for both rungs and prints what it cost.

## Suites

`scripts/suite_watch.py` with the unit suite (`-n 8 --dist worksteal`), then the four Playwright files (`-n 4`), one at a
time, rc 0, no skips; `uv run ruff check ergostat tests scripts`.

## Size budget

**600 net lines outside `tests/` and `docs/`** (the template's YAML and the prompts counted).
