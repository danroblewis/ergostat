# lease-shutdown-race: a run started as ergostat stops never keeps its lease

depends-on: []

Branch `lease-shutdown-race`, from main. Found by grooming: `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`
flakes on main because a run started while the engine is stopping keeps its lease (the take and the stop race in
`ergostat/leases/dispatch.py`'s take and `ergostat/spec/engine.py`'s shutdown). Any gap's unit run can hit it; it held
back inbox-dismiss, whose round 3 wrote a fix and two tests for it on `factory/inbox-dismiss` and was told (rightly) to
move them into their own gap. Start from that fix (in the drop as `factory/inbox-dismiss`, round 3), lifted out alone.

## Definition of done

No lease is taken once the engine has begun stopping, and a take that raced the stop is given back (uncounted) before
the engine exits, so after a restart the fold is the truth: no item is left leased by a run that never ran. The fix
holds under load: the test passes 30 runs of `-n 8` with the CPU loaded, and the restart test no longer flakes.

## Acceptance tests

- `tests/test_leases.py::test_no_lease_is_taken_once_the_engine_is_stopping`
- `tests/test_leases.py::test_a_take_racing_the_stop_is_given_back_uncounted`
- `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` (no longer flaky: 30 loaded runs)

## Size budget

120 net lines of code outside `tests/` and `docs/`.
