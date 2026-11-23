# merge-run-stages-with-times: a running pipeline says its stage, how long each took, and how long is left

depends-on: [sql-source-over-item-views]

The owner's most common question while waiting: which items are in the merge queue; if it is running, what stage it is in; how long the earlier stages took; how long the current one has run; how long it should take. "We are sort of building a CI/CD system as an ergostat model now."

What exists. Each merge batch is an item (`batch/*`) with its gaps, runs, run kind and state (testing, isolating, pushing, ...). It does not record the stages inside a run (ruff, unit, browser, host, demo, named tests, isolation rounds, the push wait), so nothing can say how long each took or how long is left.

Change. Build this as a general feature that any pipeline modelled in ergostat can use, with the merge queue as its first user.

1. A general way for a working item to record named stages: started, finished, outcome, and which attempt or run they belong to, as ordinary events. A stage can repeat, and stages can run in parallel. A process that dies leaves its stage visibly unfinished, not silently "running" forever.
2. The merge queue records every stage of a batch, including waiting for push approval.
3. Expected time for a stage is the median of that stage's recent finished runs on the same kind of run, with the sample count. Under three samples it says there is no estimate. A failed or cut-short stage does not count as a normal duration. The batch's time left is the current stage's remainder plus the remaining stages of a green run. While isolating, say that the remaining path depends on what fails.
4. **Show it on the Dashboard. This is the owner's requirement ("i want to see those on the dashboard"), and the Dashboard is the primary surface.** The default dashboard gets a "Merge queue" row, built from ordinary configurable panels and queries that a person can open, edit and copy:
   - what is in the running batch, and the approved gaps waiting, in the order they will be taken;
   - the running batch's current stage, elapsed time in that stage, expected time, and time left;
   - each stage of the running batch in order, with state and actual or expected duration, as a stage timeline or table;
   - recent batches: outcome, size, total time and time per stage;
   - typical time per stage over time.
   Per-batch and per-gap rows carry generated IDs, so they come from a read-only SQL view over the item record (`item_stages`, through the SQL data source), never from metric labels. Stage durations are also histograms labelled only by bounded names (pipeline kind, stage, outcome), queryable in PromQL. Panels refresh while a batch runs. The batch's item page may link to the same facts, but no new page is added.
5. Teach it: add to the agent guide how to model a CI/CD pipeline with these stages.

Definition of done.
1. Tests cover stage recording, repeats, parallel stages, a process that dies mid-stage, and estimates with too few samples.
2. A simulated batch that goes red, isolates a culprit and lands the rest shows every stage with correct durations.
3. A second, non-merge item kind uses the same stages in a test, proving it is general.
4. A browser test on the default dashboard shows a running batch's items, current stage, elapsed, expected and time left, and the waiting line, and each panel opens in the panel editor with its query.
5. Do not measure or change the live instance in the session.
