# regression-flake-rate-counts-excused: flake-rate counts the queue's excused flakes, and has no value with no runs

depends-on: []

## Problem

`flake-rate` reads only the gaps' `retries` over their `queue_attempts` (dev/bin/measure.py:174-176). Only triage writes `retries` (dev/bin/triage.py:77). A red run the queue itself excuses as a flake (dev/bin/queue.py:235-244) writes `flake.seen` and lands with `excused` in its `suites_queue`, but counts nowhere, so the goal `flakes-rare` (dev/model/measures.yaml:115-119) undercounts. With no runs it reads 0.0 (dev/bin/measure.py:176), which fails open (lesson 3; proposal milestone gap 3).

## Change

`flake-rate` = (triage retries in the window + queue runs in the window whose landed gaps carry `suites_queue.excused`, each run once by `batch_id`) / the queue runs in the window (distinct `run` in `queue_runs`, as merges-per-hour counts them at dev/bin/measure.py:160-164). A window with no queue runs exits 1 with no value. The docstring moves `flake-rate` into the list with no value, and the auxiliary's description in dev/model/measures.yaml says it counts both.

## Definition of done

1. An excused run raises the rate. A run excused for a batch of three counts once.
2. No runs in the window gives no value (exit 1), never 0.0.
3. Triage retries count as before.

## Files to touch

dev/bin/measure.py, dev/model/measures.yaml, tests/test_factory_measure_runs.py.

## Acceptance tests

- `test_a_run_excused_in_the_queue_moves_flake_rate`
- `test_an_excused_batch_counts_once`
- `test_flake_rate_with_no_runs_has_no_value`

## Size budget

30 net lines outside tests/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 2. Built; nothing left. The queue's finding: `test_a_run_excused_in_the_queue_moves_flake_rate` and
`test_an_excused_batch_counts_once` failed alone after main changed `flakes.say` so it writes `flake.seen` through
`event --add` and no longer to queue.py's stdout. The tests asserted it on stdout. 211b7ffd now reads it with
`Factory.flakes_said()`. main (ead497d1) is merged in. All 17 tests of tests/test_factory_measure_runs.py pass, and
ruff is clean. Each acceptance test was seen to fail when the code it guards was broken: with excused runs not
counted, both queue tests fail; with each landed gap counted rather than each `batch_id`, the batch test fails; with
0.0 returned for no runs, the no-runs test fails. Its second half also covers triage retries counting as before.
The measure changes by 4 net lines, within the 30-line budget.
