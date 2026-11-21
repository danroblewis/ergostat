# push-survives-the-run: an approved push of a green merge always runs

depends-on: []

The merge queue's `push-main` is asked under the lease of the run's own gap. When that gap does not land in its batch, the engine ends the lease with a nack ("the run ended with..."), the gap returns to `approved`, and the next queue run can lease it within seconds, before the `push-waiting` sensor (read every 15 s) closes the queue. The approval is then fenced out: "asked for under lease 11 ...; the lease now is 12: not run". It has happened twice (22:46 and 01:54 on 2026-11-21), each needing a hand push. `batch-fence` assumed a `queued` gap could not be taken again; the live record shows it can.

## Definition of done
- A `push-main` for an exact commit, once approved, runs whatever has happened to the lease of the run that asked. It stays safe because it pushes only that commit and only as a fast-forward of the remote's main.
- Fencing still applies to every other gated action.
- While a push is pending, the queue takes no gap: decided from `run/queue.json` when a lease would be taken, not from a sensor reading that can be 15 s old.
- The run's own gap, when it did not land, keeps its held outcome and is not returned to `approved` before the push settles.

## Files to touch
`dev/bin/queue.py`, `dev/model/landing.yaml`, the action fence code in `ergostat/`, `tests/test_factory.py`.

## Risks
- lesson-1: the check and the lease are one step.
- lesson-3: a queue state that cannot be read means no gap is taken.

## Acceptance tests
- `tests/test_factory.py::test_an_approved_push_runs_after_its_run_lease_moved`
- `tests/test_factory.py::test_no_gap_is_leased_while_a_push_is_pending`
- `tests/test_factory.py::test_a_gap_that_did_not_land_waits_for_the_push`
- `tests/test_factory.py::test_a_stale_push_is_refused_as_not_a_fast_forward`

## Size budget
80 net lines of code outside `tests/` and `docs/`.

## Where it stopped
Built; nothing is left. These are the choices made with no one to ask, each the most reversible one I could find:
- The fence is relaxed per action by a model key, `fenced: false` (default true), set only on `push-main`. Removing
  the key brings back today's behaviour. A test checks that `push-main` is the only unfenced action in the factory's
  model.
- The run's own gap, when it did not land and its outcome waits for the push, moves to a new gap state,
  `push-pending` (event `gap.push-pending`, in the merge queue's `to:`), so the engine acks its lease rather than
  sending it back to `approved`. I did not add `queued` to `to:`, because then a run killed mid-batch would be acked
  at `queued` and the gap stranded. No stock counts `push-pending` (it holds one gap at most), and `times.py` gives it
  no measure of its own.
- "When a lease would be taken": the engine has no hook that reads a program's file before it leases. So the check
  is made by the run itself, as its first step under the queue's lock: the gap is taken (`gap.queued`) only after
  that check, and the push is asked and written as pending in the same hold of the lock. A run that finds a push
  pending, or an unreadable `run/queue.json`, gives its lease back uncounted and says nothing about the gap. Because
  `gap.queued` now comes after the lock, the wait for the lock counts as `leased` time.
- The fast-forward guarantee is git's own non-forced push: the remote's ref update is a compare-and-swap. I added no
  separate check, because a check followed by a push would leave a race between the two.
- Files touched beyond the list: `ergostat.yaml` (the state), `ergostat/spec/ir.py` and `ergostat/actions/compile.py`
  (the key), `dev/bin/watch.py`, `brief.py` and `times.py` (the state named where `queued` used to stand for it),
  `dev/README.md`, `docs/SPEC.md`. Net 9 lines outside `tests/`, `docs/` and `dev/`, and 38 inside `dev/`.
