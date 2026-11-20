# merge-batching: the merge queue tests approved gaps in batches and bisects a failing batch

depends-on: []

Branch `merge-batching`, from main. From the owner's earlier pipeline: with several implementors, test approved gaps
together (merge N onto main, one suite run) and bisect a failing batch to find the merge that breaks it. The queue is
serial today (about 15 minutes a merge: unit 3, browser 8, demo 4); this becomes worth it once the queue's wait is the
binding constraint (around 4-5 concurrent implementors).

## Definition of done

The queue takes up to `batch` approved gaps (a setting, default 1 = today's behaviour) in rank order, merges each onto
main in turn, runs the suites once; green pushes all (each its own gated push, or one approval for the batch, say which);
red bisects (halves, re-running the suites) to the first failing merge, which is sent back with its failures, and lands
the rest. Flake triage still applies. The batch size is measured (queue wait, merges per hour) and can be raised by the
pool loop when the queue wait goal is off.

## Acceptance tests

- `tests/test_factory.py::test_a_green_batch_lands_every_gap`
- `tests/test_factory.py::test_a_red_batch_is_bisected_to_the_failing_merge`
- `tests/test_factory.py::test_batch_of_one_is_todays_queue`

## Size budget

300 net lines of code outside `tests/` and `docs/`.
