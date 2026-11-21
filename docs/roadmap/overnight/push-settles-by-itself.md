# push-settles-by-itself: A settled push is recorded without waiting for another queue run

depends-on: []

Audit 2026-11-21 (reproduced): when gap A fails in a batch, B lands and the push runs with no other gap approved, nothing starts a queue run, so A stays in `push-pending` indefinitely and the watch counts that as explained.

## Definition of done
A push that ran, failed or was denied is settled within minutes with no approved gap waiting, and the held outcome is applied. A gap in `push-pending` with no pending push is a stuck situation.

## Files to touch
`dev/bin/queue.py`, `dev/bin/watch.py`, `dev/model/landing.yaml`, `tests/test_factory.py`.

## Risks
- lesson-1: settling and a starting queue run must not both apply the outcome.

## Acceptance tests
- `tests/test_factory.py::test_a_push_settles_with_no_gap_approved`
- `tests/test_factory.py::test_a_gap_pending_with_no_push_is_stuck`

## Size budget
40 net lines of code outside `tests/` and `docs/`.

## Where it stopped
Round 2: built; nothing in the definition is left. Decisions taken with nobody to ask, each the reversible one:
- push-settler is commanded by a new sensor, `push-settleable` (`queue.py settleable`): 1 while run/queue.json holds a
  pending push or a block and `waits()` says nothing waits (the push ran, was denied, failed or cannot be read, or the
  block was remedied); 1 when run/queue.json is unreadable, so its runs fail where they can be seen (lesson-3).
- An action whose state cannot be read is read again on the next two settles (`unread` in the pending record) before it
  counts as failed and blocks the queue, rather than blocking at the first failed read.
- settle() and block() now save run/queue.json before they say their events, and `queue.py settle` stops on SIGTERM: a
  settler killed part way says an outcome at most once; killed between the save and the events, its gap stays at
  push-pending with no push carrying it, which the watch raises as stuck at once (the other half of this gap).
- Size: 74 net lines in dev/bin and dev/model (+87/-13), counting docstrings, comments and the YAML, over the 40. The
  overrun comes from the review's findings (the sensor and its auxiliary, the unread retries, saving before saying), each
  of them required to meet the definition or answer a finding. None of it goes outside the files to touch, except the
  README paragraph that describes the change.
- After round 2 the factory's `unit` suite showed one `F` at about 21%; its tail was cut before the summary, so the
  test was not named. It could not be reproduced on this branch: tests/test_factory.py alone (96 passed, 2 skipped),
  tests/test_factory_manager.py (18 passed), and every other unit test file in chunks at -n 4 and -n 8 (the range
  around 21% of the collection twice) all passed, with no F. No code was changed for it: without a named test there
  is nothing to fix, and a guessed change could hide a real race (lesson-10). If the queue's run fails again, its
  summary line names the test; that test is the next step.
- The next `unit` run failed in another way: its tail ends partway through a line at about 97%, with no `F` or `E`
  anywhere, no pytest summary and no `suite_watch` JSON line (which it prints on every exit, even when it kills a run). So
  the run was stopped from outside before pytest finished, not failed by a test. Nothing names a test or a line to fix,
  so no code was changed. Checked here: tests/test_factory.py alone passes (96 passed, 2 skipped, 172 s). Its slowest
  test, test_the_factory_model_loads (60 s, reading ergostat.yaml), takes the same 60.6 s with main's
  dev/model/landing.yaml put back for the timing (then restored), so the branch did not make it slower. The branch's own
  tests take at most 17 s (the wiring test, which reads the model) and 4 s. If the queue's run stops like this again,
  look at what stopped it (the lease, the container, memory) before looking at the branch.
- Round 3: no new finding was given; the findings listed are round 1's, each answered in round 2 and checked again
  here: push-settler is commanded by `push-settleable`, not `push-waiting` (landing.yaml); the wiring test
  test_push_settler_is_commanded_by_push_settleable exists; the README describes this wiring; an unreadable action is
  read again twice before it blocks; settle() and block() save before they say. main (e8d3e331) is an ancestor of
  HEAD. Each guarded line was broken by hand and the test watched fail, then put back (lesson-9): settleable()
  returning False fails test_a_push_settles_with_no_gap_approved; `in: auxiliary.push-waiting` fails the wiring test;
  dropping the at-once limit for an uncarried push-pending gap in watch.stuck() fails
  test_a_gap_pending_with_no_push_is_stuck. Run here: tests/test_factory.py (102 passed, 2 skipped, 242 s),
  tests/test_factory_manager.py (18 passed), ruff clean. No code was changed this round. The whole unit suite and the
  four browser files were not run here (the factory runs them under the watchdog); the two earlier queue runs that
  failed named no test (see above).
