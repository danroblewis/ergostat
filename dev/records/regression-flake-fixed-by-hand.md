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
