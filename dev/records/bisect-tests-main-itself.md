# bisect-tests-main-itself: a batch whose failure is main's is never blamed on its gaps

depends-on: []

The owner, 2026-11-22: "the last step in bisection should test that the main branch itself passes." On 2026-11-22 from 00:34 to 03:00 one test failed on main inside the queue's container, and the bisect sent every gap of every batch back; nothing merged for 2.5 hours (`dev/bin/queue.py`).

## Definition of done
1. When a batch fails, before any gap is blamed or sent back, the queue runs the failing tests by name on main (`pre`) alone, in the same container and settings. If they fail there too, no gap is sent back: the batch's gaps stay `approved`, the queue raises a pipeline situation naming main and the tests, and it takes no new batch until main passes or the tests are quarantined.
2. The check runs only the named failing tests (seconds, not a suite).
3. A test that fails on main and passes on a re-run is recorded as a flake, not blamed on main.
4. SPEC or the queue's docs say so.

## Files to touch
`dev/bin/queue.py`, `dev/bin/fac.py` if needed, tests, docs.

## Acceptance tests
- a batch failing on a test that also fails on main sends no gap back, leaves them approved and raises a situation
- a batch failing on a test that passes on main bisects as today

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built in round 1, nothing left of the definition. dev/bin/queue.py: on_main() (land(), on a red run that named tests,
before any gap is blamed), main_red() (take(), each run before a batch), held_by_main() (take()'s handler for MainRed).
Docs: queue.py's module docstring, item 6, and dev/README.md, *Batches*. Tests in tests/test_factory.py:
test_a_batch_failing_on_a_test_that_also_fails_on_main_sends_no_gap_back,
test_a_batch_failing_on_a_test_that_passes_on_main_bisects_as_today, test_main_red_clears_once_its_tests_pass_on_main,
test_a_test_that_fails_on_main_then_passes_is_a_flake_not_mains. Eight existing tests updated: each red run with named
tests now makes one more named run (the one on main), so their rerun counts and clocked allowances moved by that run.

Overrun reason: queue.py is +70 -3 (67 net), about 20 of them docstrings, the module docstring among them, which is the queue's own documentation that item 4 asks for; the code is about 45 lines.

Choices made with nobody to ask (each the more reversible one):
- "Raises a pipeline situation": the queue records an intervention of class `queue` (`intervention/queue-main-red-<sha>-<time>`), which pipeline-watch already turns into a queue trigger and so a situation (watch.py triggers()). It does not raise `situation/*` itself, and it does not use the queue's `blocked` state, because that waits for the coordinator's remedy and this hold has to clear by itself. When it clears, the queue records the intervention remedied.
- "Takes no new batch until main passes": while `main_red` stands, each run first runs the held tests alone on main's head as fetched, less any quarantined there. It takes a batch only once they pass or are all quarantined. Otherwise its lease is given back uncounted, after 10 minutes. The push-waiting sensor is left alone: if it stopped leasing, nothing would make the re-check.
- Fails closed: a re-run on main that cannot tell (None) counts as main's, and so does an unreadable quarantine list (no test quarantined). One case is left open: a first run on main that cannot tell (a test main lacks, a run that never started) bisects as before.
- The check runs once a run, before its first finding. It does not run after a gap has been blamed, and it does not see a test the red run did not name (a sibling suite stopped by the first failure). dev/README.md says both.
- If any of the failing tests fails on main twice, the whole batch is held, including when some other test passes on main.
