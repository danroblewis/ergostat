# regression-queue-test-counts: The merge queue records each suite's pytest counts, unknown when its log cannot say

depends-on: []

Problem: the queue keeps only rc, seconds and a SKIPPED count per suite (dev/bin/queue.py:111-114), so no measure can say main lost tests (regression-guarantees.md section 4). Change: a pure parser fac.counts(text) next to fac.outcomes (dev/bin/fac.py:582-588) reading pytest's final summary line from the suite's whole log, taking the last such line. In suites()'s one() each pytest suite (unit, browser, host) gains `counts: {passed, failed, skipped, deselected, errors}`; a suite with no summary line, stopped by a sibling, stalled or unreadable records `counts: "unknown"`, never zeros; a suite not run by rule (merge-pipeline-browser-only-on-its-paths) records `counts: "not_run"`, which is neither unknown nor zero. The landed run's queue_runs entry (queue.py:836-837) gains counts summed over the suites that ran, with `suites: [names]` saying which, or "unknown" if any that ran is. ruff and demo record none. Done: fac.counts parses every summary form pytest -q prints, xdist's included, and returns None without one; the existing skipped field and the browser skip rule (queue.py:111, 216-220) are unchanged; dev/README.md names the fields. Files: dev/bin/fac.py, dev/bin/queue.py, dev/README.md, tests/test_queue.py (four tests). Budget: 60 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. fac.counts (dev/bin/fac.py) reads the last pytest summary line (-q or `=`-framed, xdist's, a long run's
`(0:01:10)`, colour codes stripped, `no tests ran`), None without one. one() records `counts` on unit, browser and host
(`"unknown"` when the log has none); together() sets `"unknown"` on a sibling it stopped, even if that sibling had printed
a summary. queue.summed() gives the landed run's queue_runs entry `counts` and `suites`, taken from the green run main
ends at (the last landed gap's suites_queue). Net code lines: about 35 of 60 (dev/bin/fac.py +20, dev/bin/queue.py +15).

Decisions taken alone, the most reversible option each time:
- `"not_run"`: the rule merge-pipeline-browser-only-on-its-paths is not on main (no such code in dev/bin/queue.py), so
  nothing writes `"not_run"` yet. summed() already treats a suite with `counts: "not_run"` as not ran (left out of
  `suites`, neither unknown nor zero), so that rule only has to set it on the browser entry. A host step turned off
  (empty `[suites] host`) still has no entry at all, because tests/test_queue_host.py::test_an_empty_host_skips_the_step
  requires that. It is not written as `"not_run"`.
- Stalled or unreadable: a stalled suite raises fac.Stalled, and a log that cannot be read raises from one(), as before.
  Neither run lands and neither has a suites_queue entry to carry counts, so neither can be recorded as zeros.
- A run that lands nothing gets no `counts` or `suites` in its queue_runs entry (the definition asks only for the landed
  run's). A missing field means nothing was recorded. It is not zero.

Tests: the four in tests/test_queue.py (test_counts_reads_every_summary_form_pytest_prints_and_none_without_one,
test_a_landed_run_records_each_pytest_suites_counts_and_their_sum, test_a_suite_whose_log_cannot_say_records_unknown_
never_zeros, test_a_runs_sum_is_over_the_suites_that_ran_unknown_if_any_is). Each was seen to fail with the code it
guards broken: counts returning zeros with no summary line, a stopped sibling keeping its counts, summed dropping an
unknown suite. tests/test_queue.py (17) and tests/test_queue_host.py (12) pass. The summary forms are taken from pytest's
own output format. Running pytest on a scratch file to capture them live was refused in this session.
