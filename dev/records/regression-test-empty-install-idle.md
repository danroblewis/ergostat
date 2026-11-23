# regression-test-empty-install-idle: A test that an empty install runs nothing

depends-on: []

## Problem

Invariant 12 says an empty install runs nothing (CLAUDE.md:52-53). The proposal notes that no test checks it (proposal section 2b, U5 row). A default block, sensor or template added by accident would land green.

## Change

One test that starts the engine on an empty model (a folder with a minimal `ergostat.yaml` and no parts), steps it for a few ticks, and asserts:
- no block runs (no `agent.started`), no sensor reads, and no item is made;
- the record holds only ergostat's own start events.
The test is broken once on purpose (a stray default part added) to see it fail (lesson 9).

## Definition of done

1. The test passes on main.
2. It fails when a default part is added.

## Files to touch

tests/test_empty_install.py (new).

## Acceptance tests

- `test_an_empty_install_runs_nothing`

## Size budget

0 net lines outside tests/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
