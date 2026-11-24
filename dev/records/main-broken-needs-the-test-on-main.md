# main-broken-needs-the-test-on-main: a test main does not have is never called main's failure

The check that a gap's failing test "fails on main too" (`dev/bin/onmain.py`) recorded `tests/test_control_spike.py::test_gate_cost_per_event` as broken on main, though that file is not on main. It came from the branch or its stacked base. A test that cannot be collected on main looks the same as one that fails there, so a gap's own failure can be excused and the gap told to wait for main to move.

Change. A named test that does not exist on main, or cannot be collected there because it is missing, is not main's failure. It stays the gap's (or its stacked base's) and goes back through the normal fix path, saying which.

Definition of done.
1. Tests: a test absent from main is not main-broken; a test truly failing on main still is; a stacked gap's failure from its base names the base.
2. Existing main-broken records of tests absent from main stop holding gaps.
3. Do not measure or change the live instance in the session.
