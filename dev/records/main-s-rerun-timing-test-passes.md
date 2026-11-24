# main-rerun-timed-test-in-container: tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed passes on main in the queue's suites
depends-on: []

## Definition of done
- The test has failed on two or more main commits since 11-23 09:57 (interventions main-broken-e43046dc0cc3, -58471dafb951, -5411f137eca9, -af4bc34a9e4c, -ead497d1f4bc), and still fails after the isolation fix d3f08d49 (merged as ceaec9d1). Find the cause where it fails, in the queue's Linux container under -n with the full unit suite (module state from another worker test, dev/bin path, the room() time arithmetic against a slow container), and fix that cause in onmain/room or in the test. Raising a bound is not enough (lesson-10).
- 'Where it stopped' gives the traceback seen before the fix and says which run showed it.
- The fix is shown by the full unit suite on a merge of origin/main, in the queue's container, with this test passing.

## Acceptance tests
- tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed passes in the full unit suite on main
- a new test that reproduces the cause found (for example the state an earlier test leaves behind, or a slow clock) and fails without the fix

## Size budget
60 net lines

## Where it stopped
- Traceback before the fix. All five interventions this definition names (main commits ead497d1, af4bc34a, 5411f137, 58471daf, e43046dc, from 11-22 21:26 to 11-23 02:37 -0800) are earlier than the isolation fix's merge (ceaec9d1, 11-23 03:18 -0800). Their cause, as safe-stalls-heal-themselves rounds 3-5 also recorded on those mains, is the one d3f08d49 fixed. I saw it again here by running main's old test body (from d3f08d49^) alone in this Linux container:
  `dev/bin/onmain.py:25: import flakes` -> `ModuleNotFoundError: No module named 'flakes'` (1 failed in 0.23s).
- After the fix I saw no failure. On this branch's base (main, b7302db6) the test passes alone (2 passed with its stub test) and with the whole of tests/test_agents.py (27 passed). No queue run after ceaec9d1 with this test failing is in the clone, and the queue's logs can't be reached from it, so I have no traceback after the fix. I make no claim that the cause below ever failed a queue run.
- The cause left in the test, fixed in the test (the more reversible option: room() and onmain are unchanged, 0 net lines outside tests/ and dev/). The test read the wall clock once (`soon = time.time() + 200`), and room() read it twice more. So the test passed only while fewer than 140 s of wall time went by between those readings: a starved worker in a loaded container, or a clock another test moved. Now the test gives its own fresh onmain a fixed clock (`monkeypatch.setattr(onmain, "time", ...)`, only that module object, undone after). It also pins the boundary: room is held at exactly LEAST and given at LEAST + 1 s. Raising a bound would not have fixed this (lesson-10). The time dependence is gone.
- New test tests/test_agents.py::test_room_holds_on_a_slow_clock: a wall clock that moves 150 s on each reading. I saw it fail with main's body (`AssertionError: assert (not False and False)`, the unit case given no room) and pass with the fix.
- Not run here: the full unit suite under -n 8 in the queue's container, on a merge of main (house rule: the factory and the queue run it). main has no commits beyond this branch's base, so there was nothing to merge. Run here: tests/test_agents.py whole (28 passed), the three rerun tests by name (3 passed), ruff clean.
