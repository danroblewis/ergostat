# landing-goal-reads-the-batch: a goal says when main has stopped moving, and the current batch says why

depends-on: [merge-batch-is-an-item]

Change.
- Measures from `batch` items, each named for what it measures: minutes since main last moved, runs per batch, share of batches green on the first run, minutes lost to crashed runs, and gaps landed per hour.
- A goal holds minutes since main last moved under a threshold while approved gaps wait. It is not off when nothing is waiting.
- When it is off, its reason names the current batch, its run and the cause, for example "batch X, run 6 crashed: no space left on the temporary directory". The pipeline manager reads this rather than `run/queue.json`.
- A waiting gap's "why isn't this done?" answer names its batch and run, or how many batches are ahead of it.
- Chart-ready series, so one dashboard panel can show the merge pipeline's health.

Definition of done.
1. A test record with a stalled queue turns the goal off, and the reason names the batch, run and cause.
2. An empty queue does not turn it off.
3. Each measure is checked against a hand-worked record.
4. `ergostat check` passes on the factory's model, and the goal renders in both diagrams.

Files: dev/model/landing.yaml, dev/model/measures.yaml, dev/bin/measure.py, the why-is-it-not-done code, tests.
