# queue-lands-past-a-flake: a batch whose only failures pass alone on the same tree lands, and the flake is recorded

depends-on: []

The owner (2026-11-20): "we can disable the flakey tests, or run them without blocking and review them after", and "the merge test suite should not fail for reasons other than the sum of the commits". On 2026-11-21 the queue landed nothing for over an hour: a single timing failure in a full suite makes `land()` run `named()`; the test passes alone on the whole red tree; the batch is then bisected with every suite, so one flake costs two or three more passes of 8 to 12 minutes. Between 12:44 and 13:44, five different tests did this.

## Definition of done
1. When a red run named its failed tests and each one passes when run alone on that same red tree (`named()`), rerun them once more. If they pass both times, the batch is green and lands, with no bisect.
2. Each such test is recorded where flakes are recorded (its flake item, or `failed_tests` beside the merge), with the run, the suite and that it passed alone, so that it can be reviewed after and its count is visible.
3. A test that fails alone on the red tree, in either rerun, bisects exactly as now.
4. A red run that named no tests (a killed or timed-out suite) bisects exactly as now.
5. `tests/test_page_polling.py` is never excused this way: its failure is handled as a real failure (`dynamics-open-dom-growth` is finding out if it is a leak).
6. No more than 3 tests may be excused in one run: more than that is not a flake, and it bisects.

## Files to touch
`dev/bin/queue.py`, `tests/test_factory.py` (or the file holding the queue's bisect tests).

## Risks
- This can land an order-dependent bug. That is why each excused test is recorded, why the count is capped, and why a test that fails alone never lands.
- lesson-3: a rerun that cannot be read or has no PASSED line counts as failed.

## Acceptance tests
- a batch whose one failed test passes alone twice lands, with no bisect, and the flake is recorded
- a test that fails alone on either rerun still bisects
- four failed tests that each pass alone still bisect
- a page-polling failure is never excused
- a run that names no tests still bisects

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. `dev/bin/queue.py` is +53 / -7 (46 net, docstrings included); `dev/README.md` +5 / -1.

- **Choices (the most reversible ones, nobody to ask):**
  - "Rerun them once more" is read as two runs alone on the red tree: the first `named()` (the one there today) and one
    more. Both must be green (`passed()`: rc 0 and a PASSED line for each, lesson-3).
  - When one suite fails, the suites beside it are stopped and demo never runs. So a run is not green just because its
    failed tests passed alone. Before landing, the suites the red run did not finish (`rest()`) run on the same tree.
    If they fail, the batch bisects in full. That is one more run than "lands with no bisect" strictly asks for, but
    otherwise a flake would land code whose browser suite or demo_check never ran.
  - A failed suite that also skipped tests (a page test skipped is a failure) is never excused.
  - The flake is recorded the way triage and onmain record one: `flake.seen` on `flake/<test>`, with `times: 1`,
    `gaps`, `run` (the batch id), `suite`, `passed_alone: 2` and `log`. Each landed gap's `suites_queue` also carries
    `excused` (suite, tests, log).
  - A batch of one now runs the named tests alone too, when they are excusable. Today it runs no rerun. If they fail
    alone, the result is the same as today (queue-failed).
- **Tests changed:** `test_a_named_rerun_green_on_the_red_tree_bisects_in_full` described exactly the case this gap
  now lands. Its full-bisect path is kept by the new four-tests and page-polling tests. In
  `test_a_branch_cannot_quarantine_its_own_failing_test`, T passed alone and so would now land as a flake. It is now
  given a rerun where T fails alone, which keeps the test's point (the branch's own quarantine deselects nothing).
- **Acceptance tests** (tests/test_factory.py): `test_a_batch_whose_one_failed_test_passes_alone_twice_lands_as_a_flake`,
  `test_a_test_that_fails_alone_on_either_rerun_still_bisects` (the first rerun failing is the existing
  `test_bisect_reruns_only_the_failing_tests`), `test_four_failed_tests_that_each_pass_alone_still_bisect`,
  `test_a_page_polling_failure_is_never_excused`, `test_a_failure_naming_no_test_bisects_in_full` (existing, now also
  checks that nothing is excused).
- **Break-checked:** each guard was broken by hand and its test watched fail. The cap at 4: four-tests fails. No
  page-polling exclusion: page-polling fails. The second rerun skipped, or `passed()` reading an unreadable run as
  green: either-rerun fails. The rest of the run skipped: lands-as-a-flake fails (KeyError 'demo').
- **Not run here:** the whole unit suite and the four browser files (the factory runs them under the watchdog).
  origin/main could not be checked: the command `git branch -a ...; git merge-base --is-ancestor origin/main HEAD`
  was refused. Also refused: `git checkout -q dev/bin/queue.py` (the breaks were undone by hand, and `git status` was
  clean after) and a shell loop over the four other queue-using test files (they were run in one pytest call instead:
  24 passed).
