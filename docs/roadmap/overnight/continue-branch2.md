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

## Where it stopped

Round 2, after the factory's fast suites: `unit` failed one test again,
`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` (1 failed, 1851 passed, 69
skipped; history `['expired', 'ack']` where `['ack']` was expected). This is the same failure as round 1. No code was
changed for it, though the factory's brief said "fix the code". The reason is main's review lesson 13 (3c7eab3, "stay
inside the gap: an unrelated failure is reported, not fixed in the branch"), which was written about this exact
failure on this branch. Leaving the code alone is also the reversible choice.
- It is unrelated to this branch. `git diff main --name-only` lists nothing under `ergostat/` and not
  tests/test_leases.py; the branch changes only dev/ (bin, README, knowledge), tests/test_factory*.py and docs/roadmap.
  The code the test exercises (ergostat/leases/dispatch.py `watch`/`activity`) is identical to main's.
- Why it fails under load, from reading dispatch.py:299-350 (not proven): the lease's TTL is 1s from the take, and the
  only activity that can renew it is the first `$ERGOSTAT_CMD event` the run writes. That is a fresh Python CLI
  process. If spawning the run and importing that CLI take longer than 1s under `-n 8`, the watchdog finds nothing
  since the take, and by its own rule the expiry is correct. It is a test whose TTL races a CLI start-up, or a
  watchdog that does not count the run's start (lesson-10). Either fix changes main's lease behaviour or a main test.
- Left, for the coordinator: request a lease gap of its own (start the TTL clock at the run's actual start, or give the
  test a TTL that does not race a CLI start-up), or judge this flake against main's tree under the same load. Then the
  factory's fast suites again on this branch. The open items from earlier rounds still stand: gate 1 for this salvage
  needs the coordinator, and main (5ac297a) is not merged in.

## Where it stopped

Round 3 of gap/continue-branch2 (on de17cd6): no code changed. Each finding listed for this round, answered:
- Gate 1, "continue-branch2.md is not the branch's first commit" (the queue's line and the review's): unchanged, for
  the coordinator, as in round 2. It comes from how the salvage was set up, not from the code. The way out is to accept
  continue-branch.md (19b9998) as the definition by hand, or to request it again as `continues: continue-branch` once
  this gate is on main. Rewriting history or special-casing the gate is hard to undo, so neither was done.
- review.py:42-43/148, a stale base failing a continued gap: answered in 71c4a3b and still in place. implement.py:142
  records `built_main` on gap.built. review.py:32-49 holds a continued branch to that main, and falls back to current
  main when it is missing or not on main. `test_gate_one_accepts_a_continued_branch_definition` reviews twice after main
  moves and is never parked.
- implement.py:61 / fac.py:457, conflicts split on whitespace (lesson-12): answered in 71c4a3b. `fac.conflicted`
  (fac.py:162) runs `git diff -z --name-only --diff-filter=U` and splits on NUL.
  `test_conflicts_are_listed_whole_when_a_path_has_a_space` covers it.
- lesson-7, main not merged in: this session was refused `git merge main` again, the fourth session to be refused. Main
  is now 1f013ba (the leaserenew merge). `git diff --name-only 553b955 main` shares no file with this branch's changes:
  main changed ergostat/leases, numbers, workspaces, docs/SPEC.md, docs/GAPS.md, the review lessons and lease tests,
  while this branch changes dev/bin, dev/README.md, tests/test_factory.py and its definitions. A merge should therefore
  be textually clean. It was not tried, so that is not proven.
- The unit flake (`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`): main's
  leaserenew (05edbe5, a1fb62f) now has the watchdog expire a lease only on a second look, a grace of at least 1s after
  the first. That is the race rounds 1 and 2 described: a 1s TTL against a CLI's start-up. So the merge of main is
  expected to end it. This is not proven here, because the merged tree could not be made.

Run here, one file at a time, on this branch's tree (not merged): `tests/test_factory.py` (32 passed, 2 skipped for
want of Docker); `tests/test_factory_knowledge.py`, `tests/test_ticket_factory_daemons.py`, `tests/test_intake.py` and
`tests/test_review.py` together (69 passed); ruff clean on ergostat, tests, scripts and dev/bin. Left: main (1f013ba)
merged in by the factory or a person, then the fast suites on the merged tree; and gate 1 for this salvage, by the
coordinator.

## Where it stopped

Round 3, after the factory's fast suites: `unit` failed
`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` again (1 failed, 1851 passed,
69 skipped), the third time. No code was changed here. The fix for it is already on main, and the only way to bring it
in is the merge this session was refused (the fifth refusal of `git merge main`).
- The code it tests (ergostat/leases/dispatch.py) is identical on this branch to the merge base 553b955. Main's
  leaserenew (05edbe5, a1fb62f; merged as 1f013ba) changes dispatch.py, fold.py, measures.py and terms.py
  (116+/39-). With it, the watchdog expires a lease only after a second look, at least 1s later. That covers the race
  rounds 1 and 2 found: a 1s TTL against a CLI's start-up.
- Copying those files onto this branch by hand would put lease core code back on a branch whose review
  (review/continue-branch-2, finding 4) required it removed. It would also be a hand copy of main rather than a merge
  (inbox-dismiss-3's finding). So this was not done. The reversible step is the merge itself.
- Left: someone allowed to run `git merge` merges main (1f013ba) into this branch. The merge base and main share no
  changed file with this branch (see round 3 above), so the merge should be clean, though that has not been tried.
  Then the fast suites run again on the merged tree. Gate 1 for this salvage is still the coordinator's.

## Where it stopped

Parked by the factory (implementor, 2026-11-20 09:08).

Its fast suites failed 2 times (the kill rule); the last: the fast suites failed (unit: tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere).

```
ython

tmp_path = PosixPath('/tmp/pytest-of-dev/pytest-0/popen-gw3/test_the_watchdog_renews_from_0')

    def test_the_watchdog_renews_from_what_the_holder_does_elsewhere(tmp_path):
        """A run working in a session of its own (another item) keeps its lease on its item."""
        run = ('for i in 1 2 3 4 5; do $ERGOSTAT_CMD event --add session.said --item session/$ERGOSTAT_LEASE '
               '--data "{\\"n\\": $i}"; sleep 0.4; done; echo "{\\"event\\": \\"ticket.done\\"}"')
        p = project(tmp_path, model(run, "{ttl: 1s}"))
        p.events.add("ticket.opened", item="ticket/1", source="t")
        e = start(p)
        try:
            assert wait_for(lambda: item(p, "ticket/1").state == "done", 15)
        finally:
            e.close()
        lease = item(p, "ticket/1").fields["lease"]
>       assert [h["how"] for h in lease["history"]] == ["ack"]
E       AssertionError: assert ['expired', 'ack'] == ['ack']
E         
E         At index 0 diff: 'expired' != 'ack'
E         Left contains one more item: 'ack'
E         Use -v to get more diff

tests/test_leases.py:380: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere
1 failed, 1851 passed, 69 skipped in 265.13s (0:04:25)
{"rc": 1, "wall_s": 266.1, "peak": {"threads": 348, "rss_mb": 1710.9, "procs": 121, "worker_mb": 601.7}, "killed": null, "workers_killed": 0, "left_behind": 0}

```

## Where it stopped

Round 4 of gap/continue-branch2 (on 3eae806): no code changed. Every finding listed for this round, answered:
- Gate 1, "continue-branch2.md is not the branch's first commit": unchanged, for the coordinator, as in rounds 2 and 3.
  It comes from how the salvage was set up, not from the code. Accept continue-branch.md (19b9998) as the definition
  by hand, or request the gap again as `continues: continue-branch` once this gate is on main. Rewriting history or
  special-casing the gate would be hard to undo.
- review.py:42-43/148 (a stale base failing a continued gap): answered in 71c4a3b (`built_main` on gap.built; gate 1
  holds a continued branch to it). `test_gate_one_accepts_a_continued_branch_definition` covers it.
- implement.py:61 / fac.py:457 (conflicts split on whitespace, lesson-12): answered in 71c4a3b (`fac.conflicted`, NUL
  separated). `test_conflicts_are_listed_whole_when_a_path_has_a_space` covers it.
- review/continue-branch2-1, non-blocking, "the gap has no entry in docs/GAPS.md": answered now. GAPS.md's factory
  section names this gap, its branch, its definitions and what is left. The entry is in a different hunk from main's
  only GAPS.md change since 553b955 (the leaserenew entry near line 220).
- lesson-7 and the unit failure in tests/test_leases.py: still unanswered, for the same reason as before. This session
  was refused `git merge main` (the sixth refusal). Making the merge commit some other way (`merge-tree`,
  `commit-tree`) would get around the refusal rather than respect it, so it was not done. Main's leaserenew (in
  1f013ba) is expected to end the flake (the watchdog's second look). That is not proven here.

The branch's base is still 553b955; main is 1f013ba. Main shares only docs/GAPS.md with this branch's changed files,
in a different hunk. Left: main merged in by the factory or a person, then the fast suites on the merged tree; gate 1
for this salvage, by the coordinator.

## Where it stopped

Round 5 of gap/continue-branch2 (on 6ab01cd): no code changed. The factory's brief said "fix the code" for
`tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` (this time with the history
`['expired', 'expired', 'ack']`). The fix is already on main, and the only proper way to bring it in is the merge, which
this session was refused again (`git merge --no-edit main`, the seventh refusal). The branch's base is still 553b955,
and main is 1f013ba. The gap's title says "main merged in by the coordinator", but `git merge-base HEAD main` is still
553b955, so that merge has not happened.
- Checked this round (`git diff 553b955 main -- ergostat/leases/dispatch.py`): on main, `watch` hands an overdue lease
  to `look`, which expires it only when a pass `grace(ttl)` after the first finds it still overdue. `expire` then reads
  the lease again from the record and writes nothing if it was renewed. On this branch, the code is 553b955's: the
  first pass that finds the lease overdue expires it. Two expiries in one history fit that: each renewal is followed by
  a CLI start-up that takes longer than the 1s TTL under load. This is read from the code, not run.
- Not done, for the same reasons as rounds 3 and 4: copying main's lease files onto this branch by hand
  (review/continue-branch-2 finding 4 and inbox-dismiss-3's finding), or making the merge commit with `merge-tree` and
  `commit-tree`, which would get around the refusal rather than respect it.
- Left, outside any implementor session's reach: someone allowed to run `git merge` merges main (1f013ba) into this
  branch. The only file both sides changed is docs/GAPS.md, in different hunks. Then the fast suites run again on the
  merged tree. Gate 1 for this salvage is still the coordinator's (continue-branch.md, 19b9998, is the first commit).
