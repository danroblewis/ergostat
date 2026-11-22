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

## Where it stopped
Built, round 1. Choices made alone (the most reversible each time):
- The limits are fac.limits(), called from fac.config() (so a bad value stops whatever program reads the settings)
  and again in fac.suite before a queue or triage suite starts. A value past its ceiling, or not above 0, is refused
  with ValueError, never clamped. Fractions of a minute are allowed (the tests use 0.05). The default wall limit is
  3 x fac.SUITE_GOAL_MINUTES (15, the `suites-in-time` hold in dev/model/measures.yaml; the ceiling test checks that
  the two agree), not read from the model when the program runs.
- "Untried" here means the run's own gap's lease is given back uncounted (nack, count false, after 10m), with no
  failed gate, no findings and no send-back. Its batch-mates never left `approved`. `gap.queued` has already said
  `queue_attempts: 1` before any suite runs, as it does for every run, and that stays.
- "The run's record" is a `gap.measured` on the run's own gap: `stalled` (the suite), `stalled_why`, `stalled_test`
  (the last `path.py::name` in the log, or null), `stalled_tail` (the last 2000 characters), `stalled_batch`.
  Nothing reads `stalled_test` yet. Flagging it is left to triage, as the definition says.
- In triage, a stalled rerun says the same fields and gives its lease back uncounted, so the gap stays in
  `queue-failed` and triage takes it again. I did not use `gap.retried` (back to approved) because the
  `flakes-retried` flow counts it as a flake.
- When the run's own gap already holds an outcome (a held send-back), the stall does not nack: that outcome stands.
- Not handled: a test that hangs every time is taken again every time. No cap is placed on that here.
- The container is stopped by the finally that was already there (agents.killed by name). The tests run with
  `queue_container = false`, so they show that the process group is gone, not that a container is.
- After the fast suites: `unit` came back failed with a log that ends in eight dots, with no failing test, no pytest
  summary and no closing JSON line from suite_watch (which it always prints unless it is SIGKILLed). So the run was
  killed by a signal, not failed by a test. tests/test_queue.py and tests/test_agents.py each pass alone (9 and 9).
  Running them under -n 8 here, and timing main for comparison, were refused, so the cause was not found. The one
  SIGKILL this branch sends to a pid it may no longer own was the tests' reaped(). It signalled the stand-in's pid
  after the code under test had already killed it, and a reused pid would be someone else's group. It now kills
  only a group that is alive and still led by that pid. Whether this was the cause is not shown.
