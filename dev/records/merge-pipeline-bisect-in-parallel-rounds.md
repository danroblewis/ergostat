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

## Where it stopped

Built, round 1: land() (dev/bin/queue.py) bisects a red batch in parallel rounds when its named tests fail alone on
the red tree (after the main check), or when ruff failed (ruff per prefix); queue.prefixed() runs one round through
prefixes.run_all and reads each prefix's whole log as named() does. dev/bin: about 65 net lines (budget 120).

Choices made where the definition left room (each the more reversible; say so if they are wrong):
- Step 3 says to go back to step 1 "until the named tests pass on the whole survivor tree", but done item 1 allows
  one round for one failing merge. Read together: after a round finds its failing merge, another round runs at once
  only when a prefix after the found one failed a named test the found one did not (a second failing merge shows
  there); otherwise the one full run on the survivors is that check. A later merge that fails only the same test as
  the found one is masked in the round and caught by the full run, which starts again (it never lands red). Said in
  the docstring and dev/README.md.
- Step 4 "red with new names starts again": red with the same names starts again too (the outer loop, as today);
  never landed.
- A ruff round is never followed by another ruff round at once (ruff names no test to tell a second failure by):
  the full run's ruff step finds any left and starts a new round.
- Unknown: the first prefix that is not a pass, if unknown, makes that round serial (today's step) from the
  prefixes that passed up to the first prefix that failed (in round one, the red tree, which failed them alone). A
  later round with no failing prefix goes to the full run; round one with every prefix passing (its tree failed them
  alone just before) bisects serially over the whole batch, rather than looping full runs.
- A round's passing prefixes never land; the failing gap's `pre` is main's head before the batch (as the serial
  named-test steps do today). The allowance is checked before each round (go()).
- batch_rounds and prefix_runs (heads checked) are added to every gap's suites_queue; measure.py and times.py read
  only named suites from it, so the two integer keys change no measure.
- Existing tests whose counts follow from serial named steps were updated to the round's counts
  (test_bisect_reruns_only_the_failing_tests, test_a_test_that_fails_alone_on_either_rerun_still_bisects,
  test_a_batch_failing_on_a_test_that_passes_on_main_bisects_as_today, and the second half of
  test_a_run_past_its_allowance_lands_only_what_is_proven_and_gives_back_the_rest, which now covers done item 5: the
  round finds g, the full run on the 7 cannot start, nothing lands; plus a case where the round itself is past the
  allowance). The clocked driver charges a round as one run.

Not run here: the unit suite, the four browser files, demo_check (no example touched), a round against real Docker.
