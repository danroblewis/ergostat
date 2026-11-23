# merge-pipeline-stacks-merged-forward: When a stacked gap's base moves, the new base is merged forward into it; a conflict goes back to its implementor

depends-on: [merge-pipeline-stacked-gap-builds-on-its-base]

## Problem
A base can change after its descendant started. It may go back to fix and be approved at a new head, or triage may send it back and a fix round add commits. The descendant still holds the old reviewed sha. The queue then refuses it, or (stacks-land-bottom-up) brings in a base whose reviewed head the descendant does not hold. Nothing carries the base's new commits forward. Rebasing or squashing would discard the review history, so the owner's direction is to merge them forward.

## Change
A new program, dev/bin/stack.py, run as a block stack-forward in dev/model/building.yaml (every 5m, commanded by a sensor counting stale stacks). For each gap with stacked_on whose base's reviewed head has moved and is approved again (or whose base has landed, when there is nothing to do but update stacked_on):
- if the gap is leased, building or in review, skip it. The next implementor round merges the base itself.
- otherwise merge the new base head into the gap's branch in a scratch clone of the drop, `--no-ff`, by the factory (never a rebase or a squash), and move the drop's branch from its old tip only (update-ref old value).
- clean, on an approved gap: record the new reviewed_head with `reviewed_by: stack-forward` and the new stacked_on. The merge brings only reviewed commits, and the queue tests the result.
- clean, on a built or fix gap: move the branch, and leave the next round or review to run.
- conflict: abort and send the gap back to fix with the files (`stack_conflict`), uncounted as a failed gate. implement.py's next round merges the base again and hands the conflict to the session (its conflict brief, implement.py:147-151).
Descendants are processed bottom-up, so a stack of three moves in one pass.

## Definition of done
1. Base A re-approved at a new head: an approved descendant B gets a merge commit of A's new head, keeps approved, and its reviewed_head and stacked_on are updated.
2. A conflicting merge-forward sends B to fix with the files and is not counted as a failed gate.
3. A leased or in-review descendant is never touched.
4. A stack of three moves forward in one pass, bottom-up.
5. A drop branch that moved during the merge is refused, and theirs is kept.
6. The block and its sensor are in the model. `ergostat check` adds no finding.

## Files to touch
dev/bin/stack.py (new), dev/model/building.yaml, dev/README.md (Stacked gaps), tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_a_moved_base_is_merged_forward_into_an_approved_descendant
- tests/test_factory.py::test_a_conflicting_merge_forward_sends_the_descendant_to_fix
- tests/test_factory.py::test_a_leased_descendant_is_not_merged_forward
- tests/test_factory.py::test_a_stack_of_three_moves_forward_in_one_pass

## Size budget
150 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built: items 1 to 6. dev/bin/stack.py is 147 lines, all of them counted (blank lines and the docstring too). With
dev/ left out of the core count, fac.net_lines says 0. Choices made alone, each the more reversible one:

- The block is commanded by an expr gate, `stack-forward-when` (`stale-stacks > 0`), and keeps its `every: 5m`, as
  the simplifier is. A `goal:` with `every:` was tried first. `ergostat check` found schedule-removed on it (the
  goal's controller takes it off its clock), so there is no goal on stale-stacks.
- One pass holds the queue's lock (taken only if free; a queue run holding it means the next pass). The queue is the
  only thing that moves an approved gap, and it reads the reviewed heads it merges, so the read, the decision and
  the write on an approved gap are all under that lock (lesson-1). A reviewer or implementor lease taken during a
  pass is not locked out. The branch's update-ref old value protects the branch, and the gap's state is read again
  just before it. That narrows the window but does not close it, and no test puts a lease in it.
- An approved gap whose branch is no longer its reviewed head is left alone: merging forward would record
  unreviewed commits as reviewed.
- On a clean merge, `stacked_on` is recorded on built and fix gaps too, not only approved ones. A built gap also
  gets the merge as its `head`. review.py judges `head`, so without it the review would approve the old head, and
  the queue would refuse it because the branch had moved. These are written as gap.measured (no state change).
- A landed base (merged or closed) is dropped from `stacked_on`, and nothing is merged.
- A conflict on a gap already in fix also sends gap.sent-back (fix to fix). The flow sent-back-by-stack-forward is
  drawn from gaps-approved; built and fix gaps can be sent back too.
- A `stacked_on` that cannot be read, or that names a gap not in the record, counts in stale-stacks and is never
  moved (lesson-3). The gate then stays open, and each pass only says so on stderr until someone fixes it.
- Item 6: the existing test_ergostat_check_on_the_factory_model_reports_no_new_finding compared two copies of the
  same tree, so it could not catch a finding this gap adds. Its "before" copy now has this gap's model parts removed
  (without_stack_forward), and it caught schedule-removed before the fix. Running `ergostat check` directly in the
  shell was refused here.

Extra test, not named in the definition: test_a_branch_moved_during_the_merge_forward_is_refused_and_theirs_kept
(item 5). Each test was seen to fail when the code it guards was broken: sorting by id instead of depth
(stack of three), update-ref with no old value (branch moved), merging forward leased, building and in-review gaps
(leased).

Fast suites, after the first build failed: the build log ends part way (113 of the 206 tests in tests/test_factory.py,
one `F` among them) with no pytest summary, no FAILED line and no suite_watch line. The run was cut off, no failing
test is named, and the factory found none to run alone. Run whole and serially on this branch (main merged in,
e0019aaf), tests/test_factory.py gave 204 passed, 2 skipped (the two Docker tests), rc 0. Two things were refused
here: running the build command itself under `-n 8 --dist worksteal` (to reproduce the failure), and measuring the
sizes of the pytest temp folders. Checked in this gap's code and ruled out as a parallel-only cause:
- stack.py's lock is the test's own `paths.queue_lock` (in tmp).
- Its scratch clones are under the test's own `live/sessions`, and fac.MODEL is the test's own instance folder.
- No test in the file asserts a wall-time bound that this gap moves.
- In the tests that run the real engine on the factory's model, the block stack-forward never starts: with no
  stale-stacks reading its gate gives 0 (Engine.due).
No code was changed for it: with no failing test named, a change would be a guess. If the next build names a test, it
is answered then. If it is cut off again with no summary, the cause may be the suite container (its 2 GB /tmp tmpfs
or its 12 GB memory), which is outside this gap (lesson-13).

Second build failure: cut off again, earlier (36 results, one `F`, no summary, no FAILED line). A run that stops at a
different point each time points to the container, not to one test. Run again whole and serially here,
tests/test_factory.py gave 204 passed, 2 skipped, rc 0. Running it under `-n 8 --dist worksteal`, listing /tmp and
finding a log of the build were refused, so the failing test is still unnamed. The only change: a comment in
tests/test_factory.py that this branch had changed by mistake (`-r:pytest's`) is back to main's text. No code was
changed on a guess.

Round 2 (no review findings; main af4bc34a already merged in at 5b53c6f7, nothing newer on local main): no code
changed. Run here: ruff clean; the five stack-forward tests passed (3 in 96 s, 2 in 90 s), and so did
test_ergostat_check_on_the_factory_model_reports_no_new_finding (182 s). Refused: running one test with
`--durations`, running tests/test_factory.py whole and serially in the background (with and without
scripts/suite_watch.py), and appending this section from the shell. So this round has no whole-file number. What I
read but could not prove: the implementor's build step (fac.suite with box "") has no stall or wall limit, so a log
that stops with no pytest summary means the process died. The likely cause is an OOM kill: -n 8 in a 4-CPU, 4 GB
suite container (suite_memory_gb), with every Factory test's pytest temp folder kept for the whole session on a tmpfs
/tmp, which counts against that memory. That is outside this gap (lesson-13). If it is cut off again, the next round
needs the build log or permission to run the build command.

Next build failure: the tail ends at `affected_tests: 5 changed, running tests/test_factory.py` with no test result at
all and no suite_watch line. The run was stopped from outside before pytest printed anything, so no test is named.
This round the file was run whole and serially here (scripts/named_tests.py, no time limit): 205 passed, 2 skipped
(the Docker tests) in 1069 s, rc 0. An earlier run in this round under `timeout 900` had one failure, a SystemExit 143
in fac.py's SIGTERM handler. That came from the `timeout`'s own SIGTERM at 900 s (that run took 987 s), not from
the branch. The cut-offs happened at different points (113 results, 36, then none), and the file passes whole on its
own. Both point to the build step's container (4 CPUs, 4 GB, -n 8), which is outside this gap (lesson-13). No code
was changed on a guess. Refused here: writing the run's output to a /tmp log, and reading the running tests' processes
with ps.

Next build failure, named this time: tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine
(`assert 'switcher' not in e.running` after its 120 s wait; 1 failed, 204 passed, 2 skipped in 558 s). Run alone on
this branch it passed: 1 passed in 146 s for both switcher runs and the switch together, so each run finishes well
inside 120 s on its own. The switcher runs dev/bin/drain.py, which makes a dozen or so `ergostat item` calls. Each
one is a new process that loads the model. This gap's code is not on that path. stack.py is never started (the test
starts only the switcher, and the engine's loop does not run). The only thing this gap adds to that path is a sensor,
an expr block and a program block in the model each call loads (about 29 lines of YAML). That points to lesson-10, not
to this branch: a fixed 120 s wait on a run made of many subprocesses, overrun under `-n 8` load. Two commands were
refused, so this could not be measured: running the same test on main in a /tmp worktree
(`git worktree add -q /tmp/mainwt main`), and timing `uv run ergostat item --kind upgrade` on this model. No code was
changed and the test's bound was left alone. No cause was found in this gap, so a change would be a guess, or would be
outside the gap (lesson-13). If it fails again, it should be run on clean main under the same load. If it fails there
too, the failure is main's, not this gap's.

Round 3 (no review findings; main 7a905955 already merged in at c81fbadd, nothing newer on local main): no code
changed. Run here, serially: ruff clean; the five stack-forward tests passed, and so did
test_an_approved_switch_drains_and_switches_through_the_engine (the earlier build failure), 3 passed in 276 s and 3 in
200 s. The whole file and the build command under `-n 8` were not run this round.

Round 3 build failure: cut off again, this time after 153 results with no `F` at all, no pytest summary and no
suite_watch line. Nothing failed before the stop, so no test is named and nothing in this gap is shown wrong. This is
the fourth cut-off at a different point (113, 36, none, 153). Read again for anything of this gap's that could grow
or hang under `-n 8`: stack.py removes its scratch clone in a finally, its merge passes `-m` (no editor opens), and
the block stack-forward never starts in the tests that run the engine on the factory's model. No code was changed on
a guess (lesson-13). The likely cause is still the build step's container (4 CPUs, 4 GB, -n 8, tmpfs /tmp). To tell
main's failure from this gap's, the next round needs the build log, or tests/test_factory.py run on clean main under
the same load. Refused this round: appending this note and committing it from the shell (heredoc, then ruff and
git commit in one command).

Round 3, second build failure, named: test_an_approved_switch_drains_and_switches_through_the_engine again (the
switcher still running at its 120 s wait; 1 failed, 194 passed, 2 skipped in 697 s). This time it was measured, not
guessed. The test was given a timer for each switcher run, written only for the measurement and not committed. Run
alone with the branch's model, the two runs took 43.0 s and 42.2 s. With this gap's three model parts taken out
(dev/model/building.yaml the same as main's), they took 43.6 s and 43.8 s. So the branch adds no time to the switcher.
Its model parts cost nothing measurable, and stack.py is never started on that path. A run takes about 43 s alone
against a 120 s bound. Under `-n 8` on the build container's 4 CPUs it runs about three times slower and overruns. That
is lesson-10's fixed bound, on main's code (dev/bin/drain.py's many `ergostat item` subprocesses), which is outside
this gap (lesson-13). The ask was to fix the code, not the bound. The only code that would make the run faster is
drain.py or ergostat's start-up, and neither is in this gap's Files to touch, so it belongs in its own gap. No code was
changed. Both files were put back to the committed text and checked with git status. Refused here: `git checkout main
-- dev/model/building.yaml` (so the model parts were taken out with edits instead), a later `git checkout HEAD --`
to put them back (done with edits), and reading or piping a timing file under /tmp.

Round 4 (no review findings; main dc47a763 already merged in at f2e2fbcf, nothing newer on local main): no code
changed. Run here, serially: ruff clean; the five stack-forward tests and
test_ergostat_check_on_the_factory_model_reports_no_new_finding passed (3 in 186 s, 3 in 338 s). The whole file and
the build command under `-n 8` were not run. The earlier build failure
(test_an_approved_switch_drains_and_switches_through_the_engine, its fixed 120 s bound under load) was measured in
round 3 as no slower with this gap's model parts than without. It stays outside this gap (lesson-10, lesson-13).
Refused this round: appending this note and committing it from the shell in one command (heredoc, git add, git commit).

Round 4 build failure: the same test again (switcher still running at its 120 s wait; 1 failed, 194 passed, 2 skipped
in 580 s, peak 911 MB, nothing killed). No code was changed. Round 3 measured the branch adding no time to it (43.0 s
and 42.2 s with this gap's model parts, 43.6 s and 43.8 s without), and stack.py is not on its path. Where the time
goes, from reading dev/bin/drain.py and fac.items: each switcher step starts a new `ergostat` process (and loads the
model) for every listing. under_way() lists three kinds, and fac.items(kind) with no state makes one call for the
kind's head plus one per state it has. Add upgrade's listing, action_state and each fac.say, and one step makes well
over ten such calls. At a few seconds each under `-n 8` on 4 CPUs, two steps pass 120 s. The fix that would hold is
fewer calls in drain.py: under_way() listing only the leased states, or one listing for all kinds. That is main's
code and outside this gap's Files to touch (lesson-13), so it should be a gap of its own: "the switcher's step makes
one ergostat call per listing". It is not built here. Until it is, this gap passes alone and fails the build only when
that test overruns its bound under load, as it would on main. Refused this round: putting a temporary per-call timer
in dev/bin/fac.py from the shell (python edit, then a /tmp log), so these call costs are read from the code and not
measured.
