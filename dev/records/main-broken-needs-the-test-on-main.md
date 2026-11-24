# main-broken-needs-the-test-on-main: a test main does not have is never called main's failure

The check that a gap's failing test "fails on main too" (`dev/bin/onmain.py`) recorded `tests/test_control_spike.py::test_gate_cost_per_event` as broken on main, though that file is not on main. It came from the branch or its stacked base. A test that cannot be collected on main looks the same as one that fails there, so a gap's own failure can be excused and the gap told to wait for main to move.

Change. A named test that does not exist on main, or cannot be collected there because it is missing, is not main's failure. It stays the gap's (or its stacked base's) and goes back through the normal fix path, saying which.

Definition of done.
1. Tests: a test absent from main is not main-broken; a test truly failing on main still is; a stacked gap's failure from its base names the base.
2. Existing main-broken records of tests absent from main stop holding gaps.
3. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1 (about 70 net lines in dev/bin, within the 600). Choices taken alone, the reversible ones:

- "Main has the test" is read from git, not from a pytest collection: `onmain.present` wants the file at main and
  each `class` and the `def` of the id in it. A test only inherited from a base class, or made without a `def`, reads
  as absent, so it counts as the gap's (the side that never excuses the gap). A ref or file that cannot be read is
  also absent.
- The run on main is on main itself (`built_main`), not on the stack of main and the bases as before: a failure the
  bases bring can then never be called main's. "Names the base" covers a test that main lacks and a base has; a test
  main has that fails only on the stack is the gap's, as no extra run on the stack was added.
- Done item 2: the intake releases at once a gap whose `waits_on_main` hold lists a test (`main_broken_tests`) its
  main commit lacks, writing `not_on_main`. The `flake/<test>` items already in main-broken for such tests are left as
  they are (they hold no gap; main-mend keeps them unknown), and so are their interventions.
- Done item 3: nothing in the live instance was read or changed.
