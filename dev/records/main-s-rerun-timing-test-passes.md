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
