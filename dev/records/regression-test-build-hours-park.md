# regression-test-build-hours-park: A test that a gap past its build hours is parked

depends-on: []

## Problem

The kill rule parks a gap whose building took more than `[gates] build_hours` (dev/bin/implement.py:190-193, dev/factory.toml:17). No test parks a gap on `build_hours`. The proposal lists that part of F8 as untested (proposal section 2a, F8 row). A refactor that drops the check would land green.

## Change

One test in tests/test_factory.py, on the Factory fixture (`GATES`, tests/test_factory.py:117). A gap with `build_hours` at the limit, taken by the implementor, is parked with the kill rule's reason and starts no session. One just under the limit is built (tests/test_factory.py:1263 already folds one just under). The test is broken once on purpose (the comparison flipped) to see it fail (lesson 9), and that is said in the definition.

## Definition of done

1. The test parks at the limit and builds below it.
2. It fails with the check removed.

## Files to touch

tests/test_factory.py.

## Acceptance tests

- `test_a_gap_past_its_build_hours_is_parked`

## Size budget

0 net lines outside tests/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built. `test_a_gap_past_its_build_hours_is_parked` (tests/test_factory.py) runs the implementor on two Factory fixtures.
The first has `build_hours` at `GATES["build_hours"]` and is parked: `gap.parked` alone, parked_for kill-rule, parked_in
building, the kill rule's reason in where_it_stopped, no stand-in session's result line, no branch in the drop. The
second has the limit less 0.001 and is built: `gap.started`, `gap.built`, and a session ran.

Broken on purpose (lesson 9) in dev/bin/implement.py:191 and restored each time: the comparison flipped to `<`, `>=`
changed to `>` (the limit itself let through), and the check removed (`if False:`). Each time the test failed with
`['gap.started', 'gap.built'] != ['gap.parked']`. It passes on the restored code, and so does
`test_no_reruns_past_the_building_hours`. Not run here: the whole unit suite and the browser files, which the brief
leaves to the factory and the queue. Main has not moved in this clone, so there was nothing to merge. 0 net lines
outside tests/.
