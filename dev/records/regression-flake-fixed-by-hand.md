# regression-flake-fixed-by-hand: A person can say a flake is fixed, and the quarantine's release is one event

depends-on: [regression-flake-writes-hold-state]

Problem: a test that was deleted or renamed stays seen or main-broken forever, and so does every goal on those stocks; manage.py has a `flake` command that writes flake.seen (dev/bin/manage.py:228-233) and no way out. The quarantine's release is a bare flake.measured with quarantined: false (dev/bin/fac.py:594-598, on main today), so the record cannot tell a release from any measurement. Change: `manage.py flake-fixed TEST --why W` writes flake.fixed from seen or main-broken with fixed_by (the person) and why, and records an intervention with intervene("flake-fixed", ...) (manage.py:56); an item in neither state is refused with a message. fac.beside's release writes flake.released (quarantined: false, released_at), declared as a no-state event in the kind's comment; quarantined folds as before. Done: the command moves an item from either state to fixed and records one intervention; it refuses an unknown test or one already fixed; a release is one flake.released event after which quarantined is false; dev/README.md 'Record an intervention' lists the command. Files: dev/bin/manage.py, dev/bin/fac.py, ergostat.yaml, dev/README.md, tests/test_factory.py (three tests). Budget: 50 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built (round 1). The tests are test_flake_fixed_moves_a_seen_or_main_broken_flake_to_fixed_with_one_intervention,
test_flake_fixed_refuses_an_unknown_test_or_one_already_fixed and test_a_quarantine_release_is_one_flake_released.
The refusal test also puts a second flake-fixed in the gap between the first one's read and its write (lesson-1).
Each test was seen to fail with its code broken: the lock removed, the fixed state let through, the release written
back as flake.measured. Choices made without asking (the most reversible ones):
- flake-fixed reads, decides and writes under flakes.held() (run/flakes.lock), the lock every flake writer takes. It
  refuses an item it cannot read, and one whose `test` field is not the test given (two tests whose slugs collide).
  flakes.py is left as it is (it is not in Files).
- The intervention's class is `flake`, the same as `manage.py flake`.
- A fixed flake seen again is remade by flakes.py, which drops fixed_by. The `why` from the fix is not dropped: it is
  overwritten by the next `why` said, and stays if a writer says none. Dropping it means touching flakes.py's
  REMAKE_CLEARS, which would also drop the `why` that `manage.py flake` writes, so it is left alone.
- tests/test_factory.py: the flake fixture's model now includes the intervention kind. `.released` is added to the
  fixture fold's no-state suffixes, which test_a_branch_cannot_quarantine_its_own_failing_test needs.

Round 2. The review's one finding: the pipeline manager could call flake-fixed itself. That is now refused unless
the caller is the coordinator (BY[0], which is `pipeline-manager` in the manager's run as watch.py sets it). The
command is removed from manage.__doc__, the tool list manager.py hands the manager, and from dev/README.md's list of
its direct tools. dev/README.md 'Record an intervention' says the manager's call is refused. The refusal test now
also calls flake-fixed as `pipeline-manager` on a seen flake: refused, no intervention, the flake still seen, and
flake-fixed absent from manage.__doc__. With the guard broken, that test failed. Choice made without asking (the
most reversible one): refused outright rather than routed through the inbox. The definition says a person says it,
and refusing adds no inbox action or approved-command path. Kept at three tests, as the definition names three.

Round 2, after the failed build. The build's tail ends partway through the dots, with no FAILED line and no summary,
so it shows no failing test: the run was cut off, not failed by a test. tests/test_factory.py was then run serially
(scripts/named_tests.py). One whole-file run reached 201 passed and 2 skipped (Docker) before the session's own
900 s timeout stopped it in test_a_defect_park_is_never_resumed_by_the_program. That test and every test after it
were then run three at a time: all passed. The factory's -n 8 build command itself was refused in this session, so
the xdist run was not reproduced. No code was changed: nothing was found to fix.

Round 2, after the second failed build. This tail shows one F (no name), so a test did fail under -n 8. The likely
cause, found by reading and not reproduced (the xdist run was not run here): the tests' manage_record loaded
manage.py, which imports fac, flakes, agents, onmain and runs from sys.modules. A worker that ran the triage test
(which leaves flakes and agents there) or the test that replaces sys.modules["fac"] first gave manage a stale flakes
bound to another fac. The new tests also left their own copies there for the tests after them. manage_record now
sets all five for the test's duration only (monkeypatch.setitem) and asserts manage uses the test's own flakes and
fac. Run serially: the three acceptance tests, also after the triage test and the fac-replacing test. All passed. No
code outside tests/ changed.

Round 3. There was no new finding to answer. The review's one finding (the manager's call) was answered in round 2,
and main (5411f137) is merged in. Run here, serially: the three acceptance tests (3 passed), and the whole of
tests/test_factory.py (193 passed, 2 skipped for want of Docker, rc 0, 502 s). ruff is clean. The -n 8 build was not
run here, so it is not shown whether round 2's sys.modules fix ends the one F of the second failed build. No code
changed.

Round 3, after the failed build. The one named failure is
test_an_approved_switch_drains_and_switches_through_the_engine: a switcher run (dev/bin/drain.py, in its own process)
was still running at the test's 120 s deadline. The branch changes none of the code it runs: drain.py, fac.items and
fac.ergostat, the engine, and live.py are unchanged. In ergostat.yaml it adds only comment lines. Run serially here it
passed alone (143.8 s for the whole test). It passed again run right after the refusal and release tests (3 passed,
162.2 s). Not proven: each drain.py run makes many `ergostat item` subprocess calls (fac.items lists each kind's states
one at a time, for gap, research and situation), each loading the whole model. Under -n 8 that can pass 120 s. That
would be a load-dependent bound (lesson-10), outside this gap (lesson-13). No code was changed, and the test's bound
is left as it is. Not run: main's own timing of this test (`git worktree add -q /tmp/mainwt main` was refused in this
session), and a timed `ergostat item` call (refused as well), so neither the cause nor that main fails it too was
reproduced.

Round 3, after the second failed build. The same test failed the same way: a switcher run still in e.running at
the test's 120 s deadline (1 failed, 192 passed, 610 s). The diff against main was read again: on this test's path
(dev/bin/drain.py, live.py, fac.items, fac.ergostat, the engine, dev/model/landing.yaml) the branch changes nothing.
fac.py's one change is in beside(), which drain.py never calls; manage.py is not run by the switcher; ergostat.yaml
gains comment lines only. Run serially here it passed (1 passed, 145.5 s; 141 s of it CPU, so the test is CPU-bound
and slows with the machine's load). One thing found by reading: the switcher block's own timeout is 5m
(dev/model/landing.yaml:387), and the test waits 120 s for each of its runs. So a run the engine still counts as
healthy can outlast the test's wait when the machine is loaded. That bound is main's (lesson-10). Changing drain.py
or the test is outside this gap's Files (lesson-13), and the test's bound is not to be raised, so no code was changed.
It is left for the factory's rerun on clean main. Not run: this test on main's tree (`git archive main | tar -x -C
/tmp/mainsrc` and running it there was refused in this session), so it is not shown that main fails it under the
same load.

Round 4. There was no new review finding. main (7a44d730) is already merged into the branch (a2b6d673), and local
main is not ahead of it. Run here, serially, after the merge: the three acceptance tests (3 passed, 22.4 s), and
test_an_approved_switch_drains_and_switches_through_the_engine alone (1 passed, 116.0 s). ruff is clean. No code
changed. Not run: the whole of tests/test_factory.py, because the background command `timeout 1500 uv run python
scripts/named_tests.py tests/test_factory.py > /tmp/tf.log 2>&1` was refused in this session. The switch test's
120 s wait under -n 8 is still main's load-dependent bound (lesson-10) and outside this gap (lesson-13), as round 3
says.
