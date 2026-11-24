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

## Where it stopped

Built, round 1. 335 net lines outside tests/, docs/ and dev/ against the branch's base after its dependency
(e871aa12). Against `main` (278f54a4, already an ancestor: nothing to merge) the diff also carries
sql-source-over-item-views' own ~470 lines, which this gap depends on and which lands before it.
Overrun reason: counted against main, the diff holds the dependency sql-source-over-item-views (about 470 net lines, its own budget), so this gap's own 335 lines are within 600 and only the sum exceeds it.

What was built:
- **General: `pipeline:` on an item kind** (compile, ir, schema; refused from a library, trust.py). It declares
  `title`, `stages` (1-32 names) and optionally `waiting: {kind, state, order}`. Its items' `stages` field folds by
  merge (another rule for it is refused).
- **`ergostat/stages.py`.** Each stage is two ordinary events, with data keyed by a span id: started
  (`stage, run, run_kind, started, until`) and finished (`finished, outcome`). So a stage may repeat, and stages may
  run at once.
  - A stage with no finish is `running` only while its item is open and before its `until`. Otherwise it is
    `unfinished`.
  - Estimates are the median of the latest 20 `passed` runs of that stage, on the same kind and run kind, with the
    count. Under 3 samples there is none.
  - The time left is the running step's remainder plus the later steps of the kind's latest all-passed run. A step is
    the stages that overlapped in it.
  - Once a stage of the item did not pass, the time left is null with the note "the remaining path depends on what
    fails". It is also null, with a note, when an estimate or a green run is missing, or a stage is unfinished.
  - Stages are also given as a Prometheus histogram with only `kind`, `stage` and `outcome` labels. Undeclared stage
    names and unknown outcomes are labelled `other`.
- **The SQL source's views `item_stages`, `stage_estimates` and `item_progress`** (_itemviews.py). They are made in
  the same read transaction as the other copies. `GET /api/stages/metrics` serves the histogram in Prometheus's text
  format.
- **The default Dashboard** (dashboard.js `dashPipeline`). When a `sql` source is declared, each pipeline (two at
  most) gets a row named for its `title`. The row has five ordinary SQL panels:
  - the running item's members and the waiting line in the order taken;
  - its stages now, with elapsed, expected, samples and time left (minutes);
  - each stage of the running (else the latest) item;
  - the recent items with each stage's time;
  - each stage's median over time.

  `/api/query/fields` lists `pipelines`. The panels refresh with the dashboard's 30 s default.
- **The merge queue.** The batch kind declares `pipeline: {title: Merge queue, stages: [ruff, unit, browser, host,
  demo, named, push-wait], waiting: {kind: gap, state: approved, order: [rank, approved_at]}}` (landing.yaml). The
  root model declares `sources: record: {type: sql}`.
  - `batches.stage()` says each stage. queue.py calls it around each suite in `suites()`: the outcome is `stopped`
    when the sibling's failure stopped it, `error` for an exception. It is also called in `named()` (the tests
    alone, on main, and on each prefix).
  - `push-wait` runs from `pending()` to `pushed()`. Its span travels in the pending push, so another process (the
    settler) ends it.
  - `until` is the suite's stall and wall limits plus 600 s.
- SPEC §5a *Stages* (with §4e's view list), the agent guide's new §3n (modelling a CI/CD pipeline) and dev/README
  are updated.

Choices taken alone (the most reversible):
- **A kind key, `pipeline:`, not a convention alone.** The row needs a title and the waiting line. The histograms
  need a declared, bounded set of stage names. Dropping the key would leave the fold rule and the views as they are.
- **"pipeline kind" in the histogram's labels is the item kind.** The run kind is not a label: it comes from events
  and is not bounded. Estimates use it.
- **Tables take one dimension.** So each row's words are one column (an item, a stage and its state or note), and
  its numbers are minutes.
- **No PromQL panel on the default dashboard.** The factory declares no Prometheus. A person can add one over
  `/api/stages/metrics` once one scrapes it.
- **The green path is the latest run, of that kind and run kind, whose stages all passed.** A run cut short with all
  its stages passed would be taken as the path. That is not tested.

Acceptance tests:
- `tests/test_stages.py` (14, unit; the kind is `deploy`, not a merge batch, which is done 3):
  - `test_a_stage_is_recorded_started_and_finished_and_may_repeat`;
  - `test_parallel_stages_run_at_once_and_the_time_left_takes_the_longer_of_them`;
  - `test_a_stage_whose_recorder_died_reads_unfinished_and_never_running`;
  - `test_under_three_normal_runs_a_stage_has_no_estimate_and_a_failed_or_cut_short_one_is_not_normal`;
  - `test_once_a_stage_did_not_pass_the_time_left_depends_on_what_fails`;
  - `test_stage_durations_are_histograms_labelled_only_by_kind_declared_stage_and_outcome`;
  - the compile refusals, and the fold and fields listing.
  These cover done 1 and 3.
- `tests/test_queue_batch_item.py`:
  - `test_a_simulated_batch_that_goes_red_isolates_its_culprit_and_lands_the_rest_shows_every_stage` (done 2: every
    stage's duration exact on a set clock);
  - `test_a_red_batch_s_every_stage_is_said_by_the_queue_itself` (slow: the real queue.py and its fake suites; stage
    names, runs, outcomes, all finished).
- `tests/test_dashboard_merge_queue.py` (browser, real server; done 4):
  `test_the_default_dashboard_s_merge_queue_row_says_the_running_batch_its_stage_times_and_the_waiting_line`. It
  checks the waiting order g1, g2 (in the batch), then g4, g3 (rank), then g5 (none), and unit's elapsed, expected
  10.0, samples 3 and left about 15.3 min. Each of the row's five panels opens in the panel editor with its SQL.

Tests changed for this:
- test_sql_source and test_sql_editor pin the view list, which now includes the three views.
- test_factory's fixture fold accepts `.stage-started` and `.stage-finished`.
- test_queue_batch_item's `said()` leaves the stage events out.

Seen to fail with the code broken:
- `until` ignored: the died-mid-stage test failed (deploy/5 read `running`).
- The 3-sample floor removed: the estimates test failed (305, 2).
- queue.py's outcome not set: the real-queue test failed (unit `passed`).
- Not mutated: the dashboard's waiting order.

Run here, one file at a time, rc 0 unless said:
- unit: test_stages (14), test_sql_source (9), test_library_trust, test_spec_schema, test_dashboards,
  test_data_sources;
- browser files under the watchdog with Playwright 1.63.0, none skipped: test_dashboard_merge_queue (1),
  test_sql_editor (2), test_dashboard_page and test_panel_editor (71 with test_sql_editor);
- test_queue_batch_item (19, Playwright): all pass but one, below.
- the real queue's other files, together: test_queue, test_queue_host, test_queue_halves (86 passed).
- ruff is clean.

Failing, and not from this branch (lesson-13):
- `tests/test_queue_batch_item.py::test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run`. The Items page
  now hides finished items by default ("1 finished (partial) not shown"). That came with 2400adda (pages.js, the
  Show finished choice), on main. The test waits for a row that is hidden. This branch does not touch the Items
  page.
- `tests/test_query_engine.py::test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log`
  (`counts` best 0.100 s and 0.120 s, alone too). It is the time bound the dependency's record already saw go red
  under load. The counts path does not read anything this branch changed.

Not run here: the whole unit suite, the four browser files, the rest of test_factory.py, and `demo_check` (no
example touched).

## Entry

section: Interface

- **A running pipeline says its stage, how long each took, and how long is left** (`merge-run-stages-with-times`): a
  kind that declares `pipeline:` records named stages as ordinary events.
  - The SQL views `item_stages`, `stage_estimates` and `item_progress` give each stage, its median of the latest
    normal runs (none under 3), and each open item's time left.
  - `/api/stages/metrics` gives them as Prometheus histograms over bounded labels.
  - The default Dashboard gets a row per pipeline. The merge queue's batches are the first: the "Merge queue" row.
  - Left: a PromQL panel once a Prometheus scrapes ergostat. The green path is the latest all-passed run, whether or
    not it was cut short.
