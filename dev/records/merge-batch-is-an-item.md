# merge-batch-is-an-item: each merge batch is an item, so ergostat can show what the queue is doing

Owner, 2026-11-23, on a separate status script: "shouldn't this be observable through ergostat itself?" On 2026-11-22 the queue was stuck for three hours. ergostat could count the waiting gaps but could not say which batch was running, which run it was on, or that the run had crashed on a full temporary directory. That lives only in `run/queue.json` and raw log files.

Note: `dev/bin/queue.py` is changing (isolation by name, then halves, on main; early stopping and screening of waiting branches on the way). Merge main first, and keep the event calls small so they merge easily.

Change.
- A new item kind `batch` (`batch/<run tag>`) in the factory's model, with states `testing`, `isolating`, `pushing`, `landed`, `partial`, `failed`, `given-back`. Its events carry no logs:
  - `batch.started`: its gaps, the base commit, the size.
  - `batch.run-finished`: run number, kind (full, named, halves), which gaps it covered, outcome (passed, failed, crashed, stalled), failed and passed counts, the first failing tests (bounded), minutes, and the crash cause when there is one.
  - `batch.isolated`: the gap found, how it was found, the tests.
  - `batch.landed`: the gaps landed, the commit, the total minutes and runs.
  - `batch.ended`: the outcome, with what was given back and why.
- While a run is under way, its progress (percent through, failures so far) is readable as a measure, read from the run's log and never by replaying events.
- The batch links to its gaps, and each gap links to the batches it was in.
- A failure to record an event never fails or delays a merge.
- It appears through what exists: the Items page, the kind's list, graph and Timeline. No new page.

Definition of done.
1. A clean batch, a batch with one bad merge, a crashed run and a batch out of time each leave the correct item, states and run records (tests with a fake suite runner, in memory where possible).
2. The item index answers a batch's state and runs without reading the event log.
3. A failing event write does not change what lands.
4. The batch kind renders on Items, including its Timeline with one bar per run.

Files: dev/bin/queue.py, a small new module in dev/bin for the events, dev/model/landing.yaml, tests/test_queue_batch_item.py (new).
