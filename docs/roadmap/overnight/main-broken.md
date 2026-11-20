# main-broken: the implementor tells a test that fails on main from one its change broke

Branch `main-broken`, from origin/main at bccf2e5. The implementor (dev/bin/implement.py) parks a gap after its fast
suites fail twice, and cannot tell "the change broke a test" from "the test fails on main anyway". gap/pool-control was
parked on two failures that were main's own (`tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`,
the engine's shutdown race; `tests/test_factory_sessions.py::test_the_container_mounts_only_the_sessions_own_folder`,
failing only inside the Linux suite container). The merge queue has flake triage (triage.py); the implementor has none.
Also (the owner: "it often takes more than 1 fix round to get something merged, something like 6 or 8 is more
reasonable"): the kill rule's numbers become settings.

## Definition of done

When the implementor's fast suites fail and name tests, before the failure counts against the gap:

1. The failing tests are run again alone on the branch, in the same kind of suite container, in the suite slot. If they
   pass, they are flakes: each is a `flake` item (`flake.seen`), and the fast suites are run once more, uncounted.
2. Those still failing are run once on clean main (the commit the branch merged, `built_main`), in a clone of the drop
   at that commit, in the same kind of container and slot.
3. Every test that fails on the branch and on main is an item `flake/<test>` in a new state `main-broken` (event
   `flake.main-broken`, with the main commit and the gap): a state, not a field, because a test that fails on main is
   not flaky, its own state keeps the flake counts and flake-rate apart, and `ergostat item --kind flake --state
   main-broken` lists them. One intervention per main commit, `intervention/main-broken-<sha12>`, class `main-broken`,
   with the tests and gaps, so it feeds `interventions-trend` and the coordinator sees it.
4. If every failing test fails on main too, the failure is not the gap's: not counted toward the kill rule, no fix
   session is spent on it, and the gap is given back (uncounted) with `waits_on_main: <sha>`. The implementor's
   `takes: where` skips a gap with `waits_on_main` set; the intake clears it once the checkout's main (what the drop
   gives the implementor, and what the queue pushes to origin) is no longer that commit, and the gap is built again.
5. If any failing test passes on main, the failure is the gap's, counted as today.
6. Bounds: at most one alone run on the branch and one run on main per failure (a test already found failing on main in
   the run is not run on main again), and none when the gap's building hours left under the kill rule are fewer than
   the unit suite took (at least a minute): then counted as today.
7. dead.py's park says so when the gap's last failing tests were all main-broken.
8. Settings: `[gates] build_failures = 6` and `build_hours = 12` replace the constants FAILS and KILL_HOURS;
   `[gates] kill_after = 6` and `[ai] suite_fix_rounds = 2` are the repository's defaults. The tests set the numbers in
   their fixture and read them, never hard-code the counts.

dev/README.md, and the implementor's and reviewer's prompts ("a failure on main is reported, not fixed: lesson 13"),
say so.

## Acceptance tests

- `tests/test_factory.py::test_a_failure_on_main_too_waits_for_main` (fails on the branch and on main: not counted,
  waits, a main-broken item and an intervention, one main run, built after main moves)
- `tests/test_factory.py::test_a_failure_that_passes_on_main_is_counted`
- `tests/test_factory.py::test_a_flake_in_the_fast_suites_is_retried`
- `tests/test_factory.py::test_no_reruns_past_the_building_hours`
- `tests/test_factory.py::test_fix_then_park` and `test_failing_fast_suites_park_the_gap` reading the fixture's settings
- the factory tests, the unit suite and ruff, rc 0.

## Size budget

250 net lines (dev/, ergostat.yaml and docs; tests outside it).
