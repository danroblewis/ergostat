# a-queue-suite-that-stalls-is-stopped: a hung test no longer holds the merge queue for its 3h timeout
depends-on: []

## Definition of done
- fac.suite, when run for the queue (box queue or triage), stops the suite's process group and container when its log has not grown for [suites] stall_minutes (default 10, at most 60, checked at config time and again at run time), or when it has run past [suites] wall_minutes (default 3 x the suite-minutes goal, at most 120).
- A stopped suite is reported as a stall, not as the batch's failure: the run records stalled: <suite> with the last test the log names and its tail. The batch's gaps go back to approved, untried, and are never sent to fix for it. The test the log was on when it stalled is named in the run's record so triage can flag it.
- The lease is no longer renewed for a suite past either limit (lesson-3: an unknown state does not keep the run alive).
- README (the merge queue) says both limits and what a stall does.

## Acceptance tests
- tests/test_queue.py::test_a_suite_whose_log_stops_growing_is_stopped_as_a_stall: a stand-in suite that prints and then sleeps is killed (process group gone) after the stall limit, and the run says stalled with the gaps approved.
- tests/test_queue.py::test_a_suite_past_its_wall_limit_is_stopped: a stand-in that keeps printing past wall_minutes is stopped.
- tests/test_queue.py::test_stall_limits_have_a_ceiling: stall_minutes 1000 is refused at config time.
- tests/test_queue.py::test_a_slow_but_progressing_suite_is_left_running: a stand-in that prints every few seconds under both limits finishes with its own rc.

## Size budget
80 net lines outside tests and docs.
