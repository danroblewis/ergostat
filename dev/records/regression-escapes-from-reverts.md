# regression-escapes-from-reverts: A revert on main is recorded as an escape of the gap it reverts, and escapes-found gets a sensor

depends-on: []

Problem: the stock escapes counts reverted merges, but gap.reverted is entered only by hand (ergostat.yaml:153-154) and its inflow escapes-found has no sensor (dev/model/pools.yaml:66-69), so a revert commit on main is invisible. Change: in `upgrade.py watch` (block main-watch, dev/model/landing.yaml:358-364; dev/bin/upgrade.py:24-41) a step escapes.watch() in new dev/bin/escapes.py walks `git rev-list --first-parent` from the last commit read (run/escapes.json) to the pushed main, at most 200 commits (said when hit), looking for `This reverts commit <sha>`. A reverted commit is matched to a merged gap first by its second parent being the gap's reviewed_head, then by main_sha (main_sha is the batch's pushed head, shared by a batch's gaps and, after merge-pipeline-gaps-md-regenerated-on-land, a commit that is no gap's merge, so it identifies a gap only when exactly one gap carries it). A match writes gap.reverted with reverted: true, revert_sha, reverted_at. No match writes intervention.recorded as intervention/reverted-<sha12>, class reverted-unmatched, which dev/bin/risk.py counts as an escape as it does an unmatched main-broken (risk.py:79-88). Ids make a second read a no-op. escapes-found gets a sensor `pools.py read escapes-day`. Done: a revert is recorded once however often main-watch runs; a revert of one merge of a batch of three blames only that gap; an unmatched one still counts; check reports no flow without a sensor in pools.yaml; a git error stops only this step; README says reverts are found by main-watch. Files: dev/bin/{escapes,upgrade,risk,pools}.py, dev/model/pools.yaml, dev/README.md, tests/test_factory.py (five tests). Budget: 130 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: all five acceptance tests in tests/test_factory.py pass, and each was seen to fail with the code it
guards broken (the already-reverted skip, the reviewed_head match, risk.py's reverted-unmatched class, upgrade.py's
catch, the escapes-found sensor). About 115 net lines, within the 130 budget. Choices made alone, each the reversible one:

- "check reports no flow without a sensor in pools.yaml": `ergostat check` reports nothing about a flow that has no
  sensor (seen: with the sensor removed it is still silent), so the test checks pools.yaml's flows itself. Every
  flow is measured, has an equation, or is a block's `out:`, except factory-harm, which this gap leaves alone and
  the test names. It also runs `ergostat check` and asserts nothing is said of escapes-found.
- escapes-day is a rate per hour (SPEC: a flow's reading is per hour): the escapes found in the last 24 h, divided by
  24. It counts gap.reverted with a reverted_at, and main-broken and reverted-unmatched interventions. A gap.reverted
  entered by hand without reverted_at has no date, so it is not counted there (it still counts in the stock).
- Reverting a revert puts the work back, so it is not recorded as an escape. A gap already reverted is not recorded
  again. The unmatched intervention's id is keyed by the reverted commit, as main-broken-<sha12> is by main's.
- When run/escapes.json names a commit the checkout no longer has, main is read again from its start, 200 commits a
  run (the ids make the re-read record nothing twice). The first run on the instance reads main's whole history
  this way, 200 commits each run.
- Outside the Files list, comments and descriptions only: the gap.reverted comment in ergostat.yaml and the
  main-watch description in dev/model/landing.yaml, kept current. Also the fold harness in tests/test_factory.py
  takes the no-state event gap.reverted.

Round 2: main (ead497d1) merged in. The one conflict, in tests/test_factory.py, was main moving the fixture's fold
into fold_line(); it is resolved as main's version, with gap.reverted added to fold_line's no-state events. The five
acceptance tests and the risk test pass again after the merge. `ruff check ergostat tests scripts` is clean.

Build after round 2: the fast suite's one failure was test_an_unstacked_gap_builds_as_before (pytest's lastfailed).
The traceback ended in subprocess.run with no CalledProcessError line, so it was most likely a timeout. Run alone on
this branch it passes (188 s: three implement.py runs, about 60 s each, against a 120 s timeout per run). It runs
implement.py, agents.py and fac.py, none of which this branch changes. So it is not this branch's code: it is the
120 s bound under -n load (lesson 10), and it belongs in its own gap, not here (lesson 13). Not run on clean main
here; the factory reruns it there. No code changed for it. The whole of tests/test_factory.py ran once after the
merge: 1 failed (this test), 203 passed, 2 skipped. Later whole-file runs were refused in this session, so the
other tests were run by name, three at a time.

Build again (after 242d02f7): one F again in tests/test_factory.py under the build's parallel workers. The tail the
factory gave names no test, and pytest's lastfailed was empty here, so the test is not known for certain. Run serially
on this branch, the whole of tests/test_factory.py passes: 204 passed, 2 skipped (Docker) in 1057 s, rc 0. The one
implement.py path in reach of this branch (pools.my_turn) is unchanged; pools.measured and risk.py, which it does
change, are not called by implement.py. So no code was changed. The likely failure is still
test_an_unstacked_gap_builds_as_before's 120 s bound per implement.py run (about 60 s each when run alone) under load.
Why implement.py takes about 60 s is outside this gap (lesson 13) and belongs in its own gap. Not run on clean main
here. A note on process: a stray single-test run was started while the whole-file run was going and was stopped after
10 s, and a first whole-file run was stopped by its own 600 s limit at 34% (its last F was the test it was killed in).

## Where it stopped

Parked by the factory (dead-letters, 2026-11-23 03:01).

Its runs failed past their attempts (a dead letter):
- attempt 8: nack queue: the push of 166e5ae0fd95 (gap/graph-draws-every-dependency) is requested
- attempt 9: nack queue: the push of 76e1a9ab1945 (gap/perf-segments-item-span-first) is requested
- attempt 10: nack queue: the push of 2985c7826921 (gap/milestone-kind-and-lifecycle) is requested
- attempt 11: nack the fast suites failed (build: tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine)

Continued, round 1 (after the park): main (dc47a763) is already merged in (8ddc718e). No code changed. The five
acceptance tests pass on this branch again, and `ruff check ergostat tests scripts` is clean. The dead letter's last
attempt failed on test_an_approved_switch_drains_and_switches_through_the_engine. Run alone on this branch it passes
in 147 s. Its two switcher runs each wait at most 120 s, and the live.py switch waits at most 90 s, so under the
build's parallel workers it is close to its bounds (lesson 10). It is not this branch's code. The engine's loop is
never started there (instance_engine), so the new escapes-day sensor does not run. It starts only the switcher
(dev/bin/drain.py) and live.py, and this branch changes neither. upgrade.py changes only in `watch`, which that test
never calls. Attempts 8-10 were queue nacks waiting on other gaps' pushes, not failures of this branch. A
comparison run on clean main (a `git worktree add --detach /tmp/mainwt main`, then the named test there) was refused
in this session, so the test was not run on main here. The factory reruns it there. Why the switcher's runs take
this long belongs in its own gap (lesson 13).

Continued, round 1 (the build's failure again: test_an_approved_switch_drains_and_switches_through_the_engine). The
cause is now measured, not guessed. Each ergostat call was timed in fac.ergostat and drain.py's step (temporary code,
removed). One switcher step made 46 ergostat calls of about 0.88 s each, so 41 s a step with nothing else running.
It came from fac.items listing every state of a kind, the empty ones too: upgrade 13 states, gap 19, research 5,
situation 6, for under_way() and the waiting upgrades. Two such steps against the test's 120 s bound each ran out
under the build's parallel workers. Fixed in dev/bin/fac.py (outside the Files list, 4 lines: the factory asked for
the code to be fixed, and it is the code the test waits on). Only a state the head line counts above 0 is listed,
and a kind whose every state is 0 is the head call alone. A head line that cannot be read still falls back to one
listing, as before. New test tests/test_fac_items.py::test_an_empty_state_is_not_listed was seen to fail with the
empty states listed again. The switch test and tests/test_fac_items.py together: 9 passed in 74 s (the switch test
alone took 146 s before). tests/test_fac_items.py, test_backlog.py and test_factory_manager.py pass (63). ruff is
clean. No test bound was changed. Main has the same fac.items. The fix is the reversible one (one filter on a parsed
count).

Continued, round 2 (the review's one finding, lesson 13): the fac.items change in dev/bin/fac.py and its test
tests/test_fac_items.py::test_an_empty_state_is_not_listed are taken out. Both files are back to main's text
(`git diff main -- dev/bin/fac.py tests/test_fac_items.py` is empty). The branch now changes only the definition's
Files plus the two comment lines named in round 1. Nothing else changed.

A gap for it is proposed here, not opened: a branch cannot make another gap's branch or item, and a definition is
the first commit of its own branch. Proposed: "fac.items lists only the states that hold items". Problem: fac.items
(dev/bin/fac.py:178-185) runs one `ergostat item --kind K --state S` for every state on the kind's head line, the
empty states too. Evidence, measured in round 1 with temporary timing code since removed: one switcher step
(dev/bin/drain.py) made 46 ergostat calls of about 0.88 s each, so about 41 s a step with nothing else running.
The kinds behind it were upgrade (13 states), gap (19), research (5) and situation (6), read for under_way() and the
waiting upgrades. Two such steps against the test's 120 s bound each make
tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine fail under the build's
parallel workers, on main as well. Change: list a state only when the head line counts it above 0, and make the head
call alone when every state is 0. A head line that cannot be read still falls back to one listing. Test: a head line
with empty states shows only the non-empty state queried. Round 1 had a 4-line version of this, seen to work (the
switch test went from 146 s to within 74 s with tests/test_fac_items.py). It is in this branch's history at
55d39de7 for that gap to take.

Until that gap lands, the build's switch test may still fail under load. That failure is on main, not this
branch's code (reasons in round 1 above), so the factory's rerun on clean main should place it there.

Continued, round 2 (build after d7119763): the build failed on
tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine (the switcher still running
at its 120 s bound; 1 failed, 194 passed, 2 skipped). This is the failure the paragraph above expected. Its code fix
is the fac.items change that this round's review told the branch to take out (lesson 13). Putting it back would
reopen that blocking finding, so no code changed. The test's bounds were not changed either. The branch does not
change dev/bin/fac.py, dev/bin/drain.py or dev/bin/live.py, so the code the test waits on is main's. The failure needs
the proposed gap "fac.items lists only the states that hold items" (55d39de7 has the fix). Until that gap lands,
this gap waits on it, or on the factory's rerun on clean main to place the failure there.
