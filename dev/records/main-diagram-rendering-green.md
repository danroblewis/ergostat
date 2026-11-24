# main-diagram-rendering-green: the 15 quarantined diagram rendering tests pass again and leave quarantine

On 2026-11-24 the coordinator quarantined 15 tests of tests/test_diagram_rendering.py (main 828321bf, tests/quarantine.txt, the lines dated 2026-11-24) because they failed alone in the queue's container on main and held every batch for over four hours. One fails with `AssertionError: autoscaler: satellite-far: 10 instances, the ceiling is 0 (docs/layout-rules.md)`; another times out waiting for a response after a switch of view. They may have been failing on main for a while unseen, because the browser suite is skipped for batches that do not touch page paths.

Change. For each of the 15: find whether the code regressed (fix it) or the test is wrong or depends on how it is run (fix the test so it passes alone and in the suite), then remove its quarantine line. Record which merge broke each, if any.

Done. Each of the 15 passes run alone by id in the queue's container setup and in the browser suite; none is left in tests/quarantine.txt. Run tests by id only. Do not measure or change the live instance in the session.
