# regression-tests-passing-goal: tests-passing on main as a measure, with a goal that it does not fall over ten merges

depends-on: [regression-queue-test-counts, regression-guarantees-model]

Problem: nothing measures how many tests main passes, so a gap that skips tests, or makes them fail to collect, passes every gate unseen (regression-guarantees.md section 4). This is not the filed cx-test-ratio's count: that one counts the tests defined in the code (in the code-health cache, for the ratio of tests to code); this one counts the tests a queue run on main actually passed, which falls when a test is skipped, deselected or broken though still defined. The record says so, and the two are never summed. Change: new dev/bin/passing.py with two readings. `tests-passing` is the summed `passed` of the latest landed queue run on main whose counts cover unit, browser and host (runs where browser was not run by rule are passed over, never read as a fall), chosen by main's first-parent seq, never by time. `tests-passing-change` is the latest less the earliest such run within the last 10 seqs, each sha once, computed by the trend-by-seq helper the filed cx-trend-auxiliaries uses for the code-health stocks (measure.py:357-420), reused and if need be given a values argument, never copied. `counts: unknown` on the latest full run, fewer than two full runs in the window or no checkout gives no value (exit 1); a missing summary never counts as zero. dev/model/guarantees-passing.yaml: auxiliaries tests-passing and tests-passing-change (every 30m) and a goal tests-not-falling (>= 0, tolerance 0, on-stale off), left unserved until regression-guarantees-wired. Done: both readings come from the recorded counts by seq through the shared helper; unknown gives no value; a browser-skipped run between two full runs changes nothing; a fixture with two runs and fewer passed turns the goal off; check has no errors and the only new finding is missing-feedback@tests-not-falling; README lists the measure and how it differs from the test ratio. Files: dev/bin/passing.py, dev/bin/measure.py (the helper's argument, if needed), dev/model/guarantees-passing.yaml, dev/README.md, tests/test_factory_measure_runs.py (five tests). Budget: 70 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (2026-11-23). Choices made with no one to ask, each the most reversible:

- **The shared helper.** `code_change`'s window (by seq, latest first, each sha once, on main, within TREND merges)
  is now `measure.by_seq(cfg, by_sha)`, and `code_change` gains `values` ({sha: (seq, value)}) in place of the code
  measures' history. passing.py calls both and sorts nothing itself. The code-health trend tests pass unchanged.
- **Which run is a sha's.** A merged gap's `main_sha` and the last of its `queue_runs` that `landed`; a batch's gaps
  share the sha, so it counts once. A gap merged twice keeps only its latest merge (the fold overwrites `main_sha`).
- **Full means `suites` holds unit, browser and host.** An install with no host suite never has a value (fails
  closed); a run older than the counts (no `suites`) is passed over, never zero.
- **An unknown run that is not the latest** is left out of the change (neither a value nor a fall); on the latest it
  gives no value, as the definition says.
- **`tests-passing` has `driven-by: [+flow.gaps-merged]`** (as code-net-lines does). Without it check adds
  `auxiliary-without-causes@tests-passing`, a second new finding the definition does not allow.
- **"The only new finding"** is tested by reading the root model (`ergostat.spec.read`, what check runs) with and
  without dev/model/guarantees-passing.yaml: no error, and the difference is exactly
  `missing-feedback@goal.tests-not-falling`. `uv run python -m ergostat check` itself was refused in this session.
- Tests: the five in tests/test_factory_measure_runs.py pass, and so do test_code_health_measures.py's three trend and
  goal tests. Each new test was seen to fail when the code it guards was broken: unknown read as 0, the browser rule
  dropped, the on-main check dropped. Not run here: the unit suite and the four browser files (no page touched). The
  branch is made from main and main has not moved in this clone, so there was nothing to merge.

Size: about 67 net lines (passing.py about 40, measure.py +7, the model YAML about 20), within the 70.
