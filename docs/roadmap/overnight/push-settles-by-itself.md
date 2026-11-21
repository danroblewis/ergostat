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
