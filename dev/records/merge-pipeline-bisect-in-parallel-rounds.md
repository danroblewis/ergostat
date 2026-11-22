# merge-pipeline-bisect-in-parallel-rounds: A red batch finds every failing merge in parallel rounds of its named tests, then lands on one full run

depends-on: [merge-pipeline-prefix-runs-in-parallel, bisect-tests-main-itself, merge-pipeline-stacks-land-bottom-up]

## Problem
After finding a failing merge, land() starts a new full run on the rest (queue.py:718-722), so each failing merge costs a full run of about 9 to 13 minutes. Two batches on 2026-11-22 show the pattern:
- operating-states-20261122T094631Z: full, 3 named, full, 3 named, ... five full runs, 75 minutes;
- queue-runs-what-its-container-skips-20261122T083445Z: 08:34 to 09:46.
In both, the named tests decided each step. A ruff failure names no test, so it bisects with full runs of every suite (queue.py:698).

## Change
In land(), a red run that named tests which fail alone on the red tree (and that bisect-tests-main-itself does not hand to main) is bisected in rounds:
1. Run the named tests on every prefix at once (prefixes.run_all).
2. The first failing prefix's last merge is the failing merge. Give it to triage as now (queue-failed, pre, findings). The stacked descendants it gives back are given back with it (stacks-land-bottom-up).
3. Rebuild the survivors' heads without it, and go back to step 1 until the named tests pass on the whole survivor tree.
4. Run the full suites once on the survivors. Green lands them. Red with new names starts again.
A ruff failure is bisected the same way with ruff per prefix. A prefix that cannot tell (unknown) falls back to today's serial step for that round. The time allowance (Late) is checked before each round. Each run records batch_rounds and prefix_runs on suites_queue.

## Definition of done
1. A batch of 8 with one failing merge makes: one full run, one named run on the red tree, the main check, one parallel round, and one full run on the 7. The 7 land.
2. A batch of 8 with two independent failing merges is found in two rounds, with one final full run.
3. A ruff failure in merge 5 of 8 is found in one ruff round.
4. An unknown prefix result never counts as a pass: that round goes serial.
5. Past the allowance, only a prefix a full green run proved lands, as now.
6. The queue docstring (item 6) and dev/README.md (Batches) give the cost per failing merge.

## Files to touch
dev/bin/queue.py, dev/README.md, tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_one_failing_merge_of_eight_costs_one_parallel_round_and_one_full_run
- tests/test_factory.py::test_two_failing_merges_take_two_rounds_and_one_full_run
- tests/test_factory.py::test_a_ruff_failure_is_found_in_one_round
- tests/test_factory.py::test_an_unknown_prefix_result_falls_back_to_serial

## Risks
- A test that fails only from an interaction of two merges fails on a prefix that holds both. The later merge is blamed, as serial bisect does today. Say so in the docstring.

## Size budget
120 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
