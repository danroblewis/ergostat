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
