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

continue-branch3, round 1: no code changed. Every finding above is already answered by what is on the branch.

- The three lease findings and the scope finding: 4352f49 is reverted on the branch (02089d9), and
  `git diff main HEAD` touches nothing under `ergostat/` (0 net lines of core code). The lease fix is main's own
  (leaserenew, 1f013ba: a1fb62f writes no refused expiry, so the sweep, `ergostat.leases.expired` and the block models
  never see one). Nothing about leases is left for this gap.
- lesson-7: main 1f013ba is merged in (acd1d72) and is still the tip of main in this clone. Run on the merged tree,
  one file at a time: `tests/test_factory.py` (32 passed, 2 skipped for want of Docker); `tests/test_factory_knowledge.py`,
  `tests/test_ticket_factory_daemons.py`, `tests/test_intake.py` and `tests/test_review.py` (69 passed);
  `tests/test_leases.py` (20 passed); ruff clean. The whole unit suite was not run here: that is the factory's
  fast-suite run.
- lesson-9: with `merge_main` (implement.py) made to return before merging, all four acceptance tests failed; the code
  was then restored.
- Gate 1 for this gap itself: the branch's first own commit (first parent) is 19b9998, `continue-branch.md`, the
  original definition; `continue-branch3.md` was added last, when the branch was seeded by hand. Main's gate 1 (which
  knows no `continues`) will find it is not first. Fixing that means rewriting the branch's history, which was not
  done (the reversible choice). Once this branch is on main, a gap with `continues: continue-branch` reads the original
  definition, as this gap's definition asks.

## Where it stopped

continue-branch3, round 2: no code changed. Both findings of review/continue-branch3-1 are answered:

- docs/GAPS.md (blocking): the entry now names `factory/continue-branch3`, says main (1f013ba) is merged in (acd1d72),
  and keeps as left only the factory's fast suites on the merged tree and the coordinator's hand judgment of gate 1.
- Gate 1 (the definition is not the branch's first commit): unchanged, by choice. The branch's first own commit is
  19b9998 (`continue-branch.md`, the original definition, whose acceptance tests and budget this file repeats). Making
  `continue-branch3.md` first means rewriting the branch's history, which cannot be undone in the drop's copy, and was
  not done (nobody to ask; the reversible option). This is the case the gap itself fixes: once it is on main, a gap with
  `continues: continue-branch` has gate 1 read the original definition.
- The reviewer's own limit (it could not run tests): re-run here, one file at a time, on the merged tree:
  `tests/test_factory.py` (32 passed, 2 skipped for want of Docker); `tests/test_review.py` with
  `tests/test_intake.py` (43 passed); ruff clean on ergostat, tests, scripts and dev. Main is still 1f013ba in this
  clone, so there was nothing new to merge. The whole unit suite was not run here: that is the factory's fast-suite run.

## Where it stopped

continue-branch3, round 3. Every finding of review/continue-branch3-2, and the two of review/continue-branch3-1 that
round 2 left unanswered, with what changed:

- Correction to round 2's note: it said "both findings of review/continue-branch3-1 are answered", but that review had
  four. Round 2 answered the GAPS entry and the reviewer's own limit; it left the `update-ref` finding and the copies of
  the definition unanswered. Both are answered below.
- dev/bin/agents.py `finish` (lesson-1, lesson-12): the drop's branch now moves only from the sha the session was
  given. `publish` returns the sha it pushed; `finish` takes it as `was` and runs
  `update-ref refs/heads/factory/<branch> <head> <was>`, so a branch another writer moved during the session
  (review.park's note, another gap's finish, a second gap continuing the same branch) is refused and the drop's branch
  kept, not overwritten. implement.py passes the published sha, then each round's new head to the next suite-fix
  round. New test: `tests/test_factory.py::test_a_branch_moved_by_another_writer_during_the_session_is_not_overwritten`
  (moves the drop's branch between publish and finish). With the old value dropped from `update-ref` it fails (seen);
  restored, it passes. Not done: intake.continued still does not check that no live gap owns an existing factory/NAME.
  With the old value in place, two gaps on one branch cost a refused finish, not a lost commit; a refusal at intake
  would be a further change and was left out to stay inside the definition.
- The copies of the definition (lesson-12): continue-branch2.md is cut to a pointer to continue-branch.md plus its own
  rounds' "Where it stopped". This file keeps its copy: it is this gap's definition file, which the house rule lets
  change only by appending. When the branch lands it can be cut the same way (git keeps the text). docs/GAPS.md now
  names one definition, continue-branch.md, and the other two files as the later rounds' notes.
- Gate 1 (this file is not the branch's first commit): unchanged, for the reason given in rounds 1 and 2 (rewriting the
  branch's history cannot be undone in the drop).
- lesson-7: this clone has no `origin/main` (`git rev-parse origin/main` fails), so main could be neither merged nor
  compared here. The factory's merge before the session (this gap's own code, once on main) or the merge queue must do
  it, with the suites run again on the merged tree.
- Run here, one file at a time: `tests/test_factory.py` (33 passed, 2 skipped for want of Docker); `tests/test_review.py`
  with `tests/test_intake.py` (43 passed); ruff clean on ergostat, tests, scripts and dev. The whole unit suite was not
  run here: that is the factory's fast-suite run.
