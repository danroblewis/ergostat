# continue-branch: a gap can continue an existing branch, with main merged in by the factory

depends-on: []

Branch `continue-branch`, from main. Asked by the coordinator: gap/warm2 and gap/warm3 were parked by the kill rule
because a continued branch (seeded by hand into the drop as factory/<name>) never got origin/main merged in: the
implementor's session was refused `git merge` three times, and the reviewer (rightly, lesson-7) would not pass a branch
63 commits behind main whose daemon code had conflicted with main before. Gate 1 also failed: a continued gap's
definition file is not its branch's first commit. Today continuing a parked branch is a manual intervention
(seeding drop.git), twice tonight.

## Definition of done

A gap request may name `continues: <branch>` (an existing branch in the checkout, e.g. a parked one). The intake
fetches it into the drop as the gap's factory/<branch> (refusing names that fail the branch rule). Before every
implementor session on a branch that is behind main, implement.py (the program, not the AI) merges origin/main into the
work clone: a clean merge is committed as the factory; a conflicted one is handed to the session with the conflict list
in its brief, and the session may run `git merge`, `git add`, `git commit` and `git status` to finish it (and nothing
that reaches a remote). The fast suites run after the merge. The reviewer's gate 1 accepts, for a continued gap, the
original branch's definition file as the definition (its first commit on that branch), and checks the merge base is
current main. The README says how to continue a parked branch.

## Acceptance tests

- `tests/test_factory.py::test_a_gap_continues_a_named_branch`: the branch fetched into the drop; the implementor starts on it.
- `tests/test_factory.py::test_a_branch_behind_main_has_main_merged_before_the_session`: a clean merge committed by the program.
- `tests/test_factory.py::test_a_conflicted_merge_is_handed_to_the_session_with_its_conflicts`: the brief lists them; the allowed git commands include merge/add/commit.
- `tests/test_factory.py::test_gate_one_accepts_a_continued_branch_definition`.

## Size budget

250 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 2's fast `unit` run did not fail a test: its log stops at 98% with no `FAILED` or `ERROR` line, no pytest
summary and no watchdog JSON line, so the run was ended from outside (the container, not an assertion). No fault in the
code was found. Run alone, one file at a time: `tests/test_factory.py` (30 passed, 2 skipped for want of Docker),
`tests/test_factory_knowledge.py` (20), `tests/test_ticket_factory_daemons.py` (6), `tests/test_intake.py` with
`tests/test_review.py` (43): all pass. The whole suite was not run here (the session was refused it). Left: the
factory's run of the fast suites again, and main (e1bf9ed) merged into the branch: this session was refused
`git merge`, which is this gap's own subject (implement.py merges main before a session once this is on main).

Round 3: no code changed. Both earlier findings were already answered in round 2 (1e3b6d9): reviews are numbered
past the highest review/<branch>-N in the record (review.py `next_review`) and run logs are named by when the run began
(fac.py `run_tag`); `agents.finish` fetches the session's head to `refs/incoming/...` and moves the drop's branch only
when the head holds the definition's commit and main (the stand-in test that aborts the merge and commits covers it).
This session was refused `git merge main` again, so the branch is still based on 1845203. Main is now 3908bc2 (adds
local-settings and the $80 cap). Its overlap with this branch is `dev/README.md` and `tests/test_factory.py`, in
different hunks; no merge was tried, so no conflict is known. Re-run here, one file at a time: `tests/test_factory.py`
(30 passed, 2 skipped for want of Docker); `tests/test_factory_knowledge.py`, `tests/test_ticket_factory_daemons.py`,
`tests/test_intake.py` and `tests/test_review.py` (69 passed); ruff clean. Left, and outside this session's reach: main
merged in by a session or person allowed to run `git merge`, then the factory's fast suites on the merged tree. The
round-2 `unit` run that was cut off has not been run again.

## Where it stopped

Parked by the factory (review/continue-branch-2, 2026-11-20 07:49).

Failed its gates twice (the kill rule). Blocking findings:
- ergostat/leases/fold.py:84 with ergostat/leases/dispatch.py:317-325 and ergostat/workspaces/leases.py:111-118 (lesson-8, lesson-1): an expiry the fold refuses is still written to and kept in the record, and the engine's clock sweep (engine.py:1497 -> workspaces/leases.sweep -> on_event) takes every ergostat.lease.expired event with no check that the fold applied it. The fence is the live lease's, so pool.release (pool.py:198) does not skip it: the workspace of the run that renewed in time is moved to held and marked fenced, and the next lease can take it. The commit's claim 'only an applied expiry releases resources' holds only for the dispatcher's own call. Either do not write the expiry when it would be refused (re-read under the fold's ordering) or make every consumer of lease.expired skip refused events, with a test that runs the sweep after the refused expiry and finds the workspace still in use.
- ergostat/leases/measures.py:42,71 and ergostat/numbers/blockmodels.py:247: refused expiries are counted in ergostat.leases.expired, in the owner's attention list ('expired') and in block models, so a renewal that won the race shows up as an expiry: false alerts and wrong measures.
- docs/SPEC.md:2101 and 2174-2180: the expiry event's new `renewed` field and the fold's refusal of an expiry written after a renewal are not documented, and SPEC still tells anything holding a resource to release on every lease.expired event (house rule: keep SPEC current with the change).
- 4352f49 (scope): a change to the lease watchdog and fold in ergostat core is unrelated to this gap's definition of done (continuing a branch, merging main), is not in its acceptance tests, and is not mentioned in its 'Where it stopped'. Main is what people install, and this is the only core code on the branch. Take it off this branch and make it a gap of its own with its own definition.

## Where it stopped

Round 1 of gap/continue-branch2 (the salvage): no code changed. The coordinator's salvage answers every finding of
review/continue-branch-2; this session checked each one.
- The three lease findings (fold.py/dispatch.py/workspaces/leases.py; measures.py/blockmodels.py; SPEC's `renewed`
  field) and the scope finding: 4352f49 is reverted (02089d9). `git diff 553b955 HEAD` touches no file under
  `ergostat/` and not docs/SPEC.md. The branch changes only dev/bin (agents, fac, implement, intake, queue, review),
  dev/README.md, tests/test_factory.py and its definition files. If the lease change is wanted, it needs a gap of its own.
- lesson-7: main (553b955, the kill3 merge) is merged in (445f3b1), so the merge base is current main.
- Checked, not changed: gate 1 as this branch would meet it. A gap that `continues` a branch works on that branch's
  own name (fac.branch_of), so gate 1 reads that branch's definition. This salvage gap is named continue-branch2, though,
  and this file is its last commit, not its first (the first on its first-parent line is 19b9998,
  continue-branch.md). The mechanical gate 1 may therefore report "continue-branch2.md is not the branch's first
  commit" unless the coordinator reviews it as `continues: continue-branch` or accepts continue-branch.md as the
  definition. Nothing was changed to get around it: the coordinator made that choice, and editing the gate for one
  salvage would be beyond this definition.

Run here, one file at a time, on the merged tree: `tests/test_factory.py` (31 passed, 2 skipped for want of Docker);
`tests/test_factory_knowledge.py` with `tests/test_ticket_factory_daemons.py` (26 passed); `tests/test_intake.py` with
`tests/test_review.py` (43 passed); ruff clean. Not run here: the whole unit suite and the browser files (the factory
runs the fast suites after this session), and the lease/workspace tests (refused to this session; those files are
identical to main's).

## Where it stopped

Round 1, after the factory's fast suites: `unit` failed one test,
`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` (1 failed, 1850 passed: history
`['expired', 'ack']`, where `['ack']` was expected). No code was changed for it here, which is the reversible choice:
- The code it tests is main's own. `git diff main --name-only` lists only dev/README.md, dev/bin (agents, fac,
  implement, intake, queue, review), tests/test_factory.py and the two definition files: nothing under `ergostat/`,
  and not tests/test_leases.py.
- Alone it passes: the test by itself (1 passed), and the whole of tests/test_leases.py (20 passed).
- Why it may fail under load (lesson-10), from reading dispatch.py, not proven: the lease's TTL is 1s. The watchdog
  renews it only from activity since the last renewal (`activity`, dispatch.py:331), and each activity is a fresh
  `$ERGOSTAT_CMD event` process started 0.4s after the last. Under `-n 8` with other suites running, if starting that
  process takes more than about 0.6s, the watchdog's next pass finds the holder silent past its TTL. By the
  watchdog's rule that expiry is correct, and a second lease then finishes the item, which explains the
  `['expired', 'ack']` history.
  The fix is either in the test (a TTL that does not race a CLI's start-up) or in the watchdog (counting a holder's live
  process as activity). Either one is a change to main's lease behaviour or to a main test. Review/continue-branch-2
  blocked exactly that kind of change on this branch (finding 4: "take it off this branch and make it a gap of its own"),
  so it is left for a gap of its own.
- Left: that lease gap, and the factory's fast suites run again on this branch. If the flake recurs, the coordinator
  should judge it against main: the same test on main's tree under the same load.

## Where it stopped

Round 2 of gap/continue-branch2 (71c4a3b). Each finding of review/continue-branch2-1 and of the queue, answered:
- Gate 1, "continue-branch2.md is not the branch's first commit" (both the queue's line and the review's): not
  changed, and it needs the coordinator. It comes from how the salvage was set up (a new gap name on the old
  branch), not from the code. Two ways out: accept continue-branch.md (19b9998, the first commit) as the definition
  by hand, or, once this is on main, request it again as `continues: continue-branch`. Changing the gate for one
  salvage, or rewriting history so a different file comes first, would be outside this definition and hard to
  undo, so neither was done. The near-copy second definition file stays for the coordinator to drop when merging.
- review.py:42-43/148, a stale base failing a continued gap after a paid session: fixed. implement.py records
  the main it merged as `built_main` on gap.built. Gate 1 now requires a continued branch to hold that main, not
  the main of the moment. If `built_main` is missing or not on main, it falls back to current main (the worst case,
  lesson-3). Main moving on after the build is left to the merge queue, which merges into the main of its moment and
  runs the suites again. This takes the most reversible reading of the definition's "checks the merge base is
  current main": current as of the build, and as of the queue's merge. The README says so.
  `test_gate_one_accepts_a_continued_branch_definition` now has main move after the build and reviews the gap twice
  more: both approved, never parked. A `built_main` the branch does not hold is still sent back. With the
  fix disabled (built_main ignored), the test fails at the first re-review.
- implement.py:61 and fac.py:457 (lesson-12, from review/continue-branch-1): conflicted files now come from
  `fac.conflicted` (`git diff -z --name-only --diff-filter=U`, split on NUL, with no strip). implement.py, the
  stand-in and queue.py:175 all use it. New test: `test_conflicts_are_listed_whole_when_a_path_has_a_space`. It
  fails when the list is split on whitespace (`['my', 'app.py']`).
- Non-blocking (lesson-7): main 5ac297a (lesson 13, tests/test_factory_knowledge.py) is 5 commits past the merge
  base 553b955 and does not touch this branch's files. This session was refused `git merge main` again. Left for
  the factory's merge before the next session, or for the queue.
- Non-blocking (lesson-10/13): the tests/test_leases.py flake under load is still a gap of its own that nobody
  has requested yet. Nothing here touches it.

Size: about 20 net lines of code in dev/bin this round. Run here, one file at a time: `tests/test_factory.py`
(32 passed, 2 skipped for want of Docker); `tests/test_factory_knowledge.py` with
`tests/test_ticket_factory_daemons.py` (26 passed); `tests/test_intake.py` with `tests/test_review.py` (43 passed);
ruff clean. Not run: the whole unit suite and the browser files (the factory's job), and anything after a merge of
main (refused).
