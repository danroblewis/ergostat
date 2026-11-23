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

## Where it stopped

Built, round 1. Main had not moved past this branch's base (`git rev-list --count HEAD..main` is 0), so there was
nothing to merge.

What is where:
- `dev/bin/landing.py` (new): the measures, the goal's reason and the current batch, read from the `batch` items and
  the gaps waiting. `measure.py NAME` reads them, and `measure.py main-stalled-why` prints the reason.
- `dev/model/measures.yaml`: `main-still-minutes`, `batch-runs`, `batch-first-green`, `crash-lost-minutes` and
  `gaps-landed-per-hour`. `dev/model/landing.yaml`: `main-stalled-minutes`, the goal `main-moving` on it, and the
  dashboard `landing.merge-pipeline` (one chart panel of all six series).
- `ergostat/why/within.py` (new; SPEC §5a, *place*): a waiting item's place, as the why answer and its summary give it.

The choices I made alone, each the most reversible I saw:
- **The goal's reason.** ergostat has no reason field on a goal. Its crossing (`loop.off`) records only the value,
  setpoint and error. So the reason is one command, `measure.py main-stalled-why`, named in the goal's description.
  The pipeline watch appends it to its `no-merge` condition (`watch.py`), and the pipeline manager's brief shows it
  with the current batch's fields under *The merge queue*, where `run/queue.json` was (`manager.py merge_queue()`).
  The watch still reads `run/queue.json` for `blocked` and `pending`, which no batch item carries.
- **The goal reads a measure of its own.** `main-stalled-minutes` is the minutes since main last moved, counted only
  while gaps wait (approved, queued, or leased by merge-queue). It starts at the later of main's last move and the
  oldest waiting gap's `approved_at` (else when it entered its state), so a gap approved after a quiet week is not
  off at once. With nothing waiting it is 0, so the goal can never be off then. The plain minutes since main last
  moved is `main-still-minutes`.
- **The threshold**: `<= 120`, tolerance 30, so off past 150 minutes. That allows a batch's suites and a round of
  halves. To change it, edit one line in landing.yaml.
- **When main moved.** `batch.landed` now carries `landed_at`. That is one line in `dev/bin/batches.py`, outside the
  Files list. A batch from before that field counts from its `started_at`, which is earlier, so the wait is never
  read shorter than it was. With no batch ever landed, `main-still-minutes` has no value (exit 1), and so do
  `batch-runs` and `batch-first-green` with nothing to measure. Never 0.
- **Windows.** `gaps-landed-per-hour` is over the last 24 hours, per hour, as a pipeline-health panel wants. The
  others use measure.py's 14 days: `batch-runs` over the batches ended in the window, `batch-first-green` and
  `crash-lost-minutes` over the batches started in it. `crash-lost-minutes` counts runs whose outcome is `crashed`
  only, not `stalled`.
- **The why answer stays generic** (SPEC: nothing in `ergostat/why/` names a kind). It reads the relations that
  declare an `inverse` and name the item's kind (in the factory, only `batch.gaps`). "In": the unfinished items
  naming it, with their state and their kind's first three `show:` fields (for a batch: size, run, outcome). "Ahead":
  the unfinished holders that name an item of its kind in its own state. So an approved gap behind a batch that
  tests approved gaps reads "1 unfinished batch item ahead of it". It is not counted ahead of a batch of one, whose
  only gap is `queued`. Its why root (the merge-queue pool full, or the gate) still explains that case.
- **Outside the Files list**: `dev/bin/batches.py` (`landed_at`), `dev/bin/watch.py` and `dev/bin/manager.py` (where
  the manager reads the reason), `dev/model/manager.yaml` (pipeline-watch reads `goal.main-moving`, which is what
  draws it in Blocks), `ergostat/web/static/pages.js` (the item page's why redraw signature includes `place`, so a
  new run of the batch redraws it), `dev/prompts/pipeline_manager.md` (two sentences), SPEC §5a and dev/README.md.

`ergostat check` passes on the factory's model (`ok`, no error). It reports nothing about any new part, and no
warning names one (`test_ergostat_check_passes_on_the_factory_model_and_says_nothing_of_the_new_parts`). One `note`
about the whole system, `system-splits` for `landing` ("its parts fall into 3 clusters with 2 links between them"),
lists one of the new parts in a cluster. I could not read its full text here, and I did not compare it with main's.
`tests/test_factory.py::test_ergostat_check_on_the_factory_model_reports_no_new_finding` passes too.

Size: 91 net lines outside tests/, docs/ and dev/ (within.py 83, the why hooks 8, pages.js 0). No overrun.

Run here, serially, with rc 0: tests/test_landing_goal.py (13 passed), tests/test_factory_manager.py (33),
tests/test_why.py and tests/test_queue_batch_item.py (with the manager file, 82 passed and 1 skipped: the
batch-item browser test, without Playwright in that run), the two check tests above, and
`ruff check ergostat tests scripts` plus the touched dev/bin files (clean).
Seen to fail with the code broken: the empty-queue test with `main-stalled-minutes` counting while nothing waits, the
stalled-queue test with the crash's cause dropped from the reason, and the place test with the same-state filter
removed. I did not mutate the diagrams test or the dashboard test. The dashboard is checked as compiled (its refs),
not drawn in a browser.

Browser: tests/test_items_page.py under Playwright 1.63.0 and the watchdog: 67 passed, 1 failed. The failure is
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (a `wait_for_function` on the header's
`#running` text times out after 30 s). It failed twice in the file and once alone. It also failed alone with this
branch's ergostat changes taken out (pages.js's line put back and `place()` not called). It runs
`examples/first-loop`, which has no relation for `place` to read and none of the new factory parts. So it is not
this branch's (lesson 13), and it is left alone. Not run here: the unit suite, the other three browser files, and
demo_check (no example touched).
