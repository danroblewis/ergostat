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
