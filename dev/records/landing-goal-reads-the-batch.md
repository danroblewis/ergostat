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

### Sent back before the suites: `interface system.managing`

The check found `interface` on `system.managing`, on the branch and not on main. Pipeline-watch (system `managing`)
reading `goal.main-moving` (then in `landing.yaml`, system `landing`) added a tenth information link across
managing's boundary, which reaches `WIDE` (10, `ergostat/spec/architecture.py`). The fix is a move. The goal
`main-moving` now sits in `dev/model/manager.yaml`, beside `merge-pipeline-flowing`, which is the same kind of goal
(the manager's view of the pipeline, read by the watch). So the watch's read stays inside `managing`. A goal reading an
auxiliary in another system is not a port (`Spec._interfaces` counts block reads and targets only), so
`main-stalled-minutes` staying in `landing.yaml` crosses nothing new. The goal's name, setpoint, tolerance, the
watch's `in:` edge (what draws it in Blocks) and every test are unchanged. This is the most reversible choice: moving
the goal back is one block of YAML. Removing the edge instead would have taken the goal out of Blocks (done item 4).
The `allows-findings` line was not touched (there is none). In this session Bash was refused, every command of it.
So I could not run `ergostat check`, the tests, ruff, or `git commit`. The edits are in the working tree, uncommitted.
The fix is reasoned from the check's code, and no run has confirmed it yet.

### Sent back before the suites: `system-splits system.managing`

Moving `main-moving` into `managing` (the fix for `interface system.managing` above) put a new goal and its edge to
pipeline-watch in managing's graph, and the check then found managing's parts splitting into clusters. Both findings
come from placing the goal so that pipeline-watch's `in:` reads it. The fix is to place it where neither can happen.
The goal is back in `landing.yaml` (system `landing`, beside its measure `main-stalled-minutes`, as at 701e1d91, when
`interface` was the only finding), and pipeline-watch's `in:` no longer lists it. Managing's parts and links are
then main's again, and main has no split. The information links across its boundary are main's 9, under `WIDE`.
The watch still reads the reason in its code (`watch.py`, the broken no-merge condition), and the manager's brief
reads it through `manager.py`. So nothing the definition asks for depended on the edge. Blocks does not need it
either. The note above was wrong to say so: `blockdiagram.py` draws a reference and a summing junction for every goal,
including one nothing reads (lines 424-461), and `test_the_goal_renders_in_both_diagrams` pins it. The model test now
asserts the goal is in `landing` and not in the watch's `in:`. This is the most reversible choice: the edge is one word
to put back. The `allows-findings` line was not touched (there is none).
Not run here: Bash refused `uv run ergostat check dev/model > /tmp/check.txt 2>&1; echo $?`, a `ps` to watch a test,
and a heredoc append to this file. Only git commands and one named test ran. So the fix is reasoned from
`ergostat/spec/architecture.py` and the branch's two earlier states, and no run has confirmed it.

### Round 2: main merged, and the unconfirmed fix above corrected

Main (b7302db6) merged. `dev/model/landing.yaml` conflicted twice, with main's `browser-main-green` auxiliary and
goal beside this branch's `main-stalled-minutes`, `main-moving` and the `merge-pipeline` dashboard. Both sides are
kept (ad379a94).

The fix above was wrong. Run at last, it failed two acceptance tests. With nothing reading `main-moving`, check
found `missing-feedback` ("no block reads it", `ergostat/spec/findings.py`), and the Dynamics diagram drew no
`main-moving` node. Blocks's reference for an unread goal doesn't make up for that. The goal is now read inside
`landing` by `merge-queue`, the block whose merges move `main-stalled-minutes`
(`in: [block.queue-when, goal.main-moving]`). Its loop closes through `flow.gaps-merged` with `merge-queue` as
controller, and no edge crosses managing's boundary. The read is not a command: merge-queue `takes:` its items, so
`engine.due` never starts it on a command (`commanders_of` counts block outputs only). It is read the way
`browser-daily` reads `goal.browser-main-green`. Nothing in `queue.py` reads the goal. The pipeline watch reads the
reason in code. Most reversible: one word in one `in:` list. The model test now pins the read and the controller.

Run here, serially, rc 0 unless said: tests/test_landing_goal.py (12 passed: the check test and the diagrams test
among them), `tests/test_factory.py::test_ergostat_check_on_the_factory_model_reports_no_new_finding` (passed),
tests/test_factory_manager.py, tests/test_queue_batch_item.py and tests/test_why.py (82 passed, 1 skipped for want of
Playwright), and `uv run ruff check ergostat tests scripts` (clean).

Under Playwright 1.63.0 and the watchdog, tests/test_queue_batch_item.py: 15 passed, 1 failed (rc 1):
`test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run`. It times out after 60 s waiting for
`table.items tr.click` on a snapshot of `#/items?kind=batch`. It failed three times alone. It also failed with
`landed_at` taken out of `batches.py`, and again with `pages.js` put back to main's line. Both are restored and
nothing of the experiment is committed. Of this branch, the test reads only `landing.yaml`'s `items:` section (the
same as main's) and `batches.py`. The snapshot and the list page never call the why answer (`place`). So it is not
this branch's (lesson 13), and it is left alone. Round 1 never ran it with Playwright. I could not run it on main:
Bash refused `git worktree add --detach /tmp/mainwt main`. Not run: the unit suite, the four browser files, and
demo_check (no example touched).

### Round 3: the review's two findings

Main had not moved (`git rev-list --count HEAD..main` is 0), so there was nothing to merge.

- **measure.py on the real clock** (tests/test_landing_goal.py, the measure.py test). The subprocess now runs
  measure.py as `__main__` through `runpy`, with `time.time` fixed at the record's `NOW` (`CLOCKED`). No reading
  depends on the date the suite runs. The test also runs it at `NOW + 20 days` and reads 0 crash-lost minutes, so a
  clock that is not the one given fails it. measure.py is unchanged. This is the most reversible fix: test only.
- **A leased gap was not counted ahead** (`ergostat/why/within.py`). A named item that is `leased` now counts in the
  state it was taken from: the `from` of its last move into `leased`, read from the item index's moves. This is the
  same reading as SPEC §9.5 and `process.unleased`, so nothing in it names a kind. If that state can't be read, the
  item counts as `leased`, which is never a waiting gap's state. That case undercounts, and nothing is made up. The
  same-state rule stays, so a batch of a `queued` gap is still not ahead of an approved one. The test adds the
  queue's own batch of one: `gap/r`, approved and then taken by a lease (`TAKEN`), in `batch/r-6`. A later approved
  gap's answer reads "ahead of it: 1 unfinished batch item, the latest batch/r-6 (testing; size 1)".
  Seen to fail with the code broken: with the leased gap left as `leased`, the new assertion fails (ahead is `{}`).
  With the same-state rule dropped, the `queued` batch assertion fails.

Size: within.py +16 net (19 added, 3 removed). That makes 107 net lines outside tests/, docs/ and dev/, well under 600.

Run here, serially: tests/test_landing_goal.py (12 passed, rc 0), tests/test_why.py with
tests/test_queue_batch_item.py and the place test (49 passed, 1 skipped for want of Playwright, rc 0), and
`uv run ruff check ergostat tests scripts dev/bin/measure.py dev/bin/landing.py` (clean). Under Playwright 1.63.0
and the watchdog, tests/test_queue_batch_item.py: 15 passed and 1 failed (rc 1). The failure is
`test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run`, the same timeout on `table.items tr.click` as
in round 2. It is left alone for round 2's reasons (lesson 13): the snapshot's list page never calls `place`.
One note, not followed up: the test fixes its batch id at `batch/a-20261123T100000Z` but takes its clock from
`time.time()`, so it may depend on the date. Bash refused a run in the background and a wait loop on its
output. Not run: the unit suite, the four browser files, demo_check (no example touched), and the `ergostat check`
tests in tests/test_factory.py (no model file changed this round).

### Round 4: main (059ff718) merged

`ergostat/web/static/pages.js` conflicted on two lines of `pageItem`. Main had added `|| late()` to the why answer's
connected check. The branch had added `w.place` to the why signature. Both are kept (f320addf). The branch's whole
pages.js diff against main is still that one `w.place`. `git rev-list --count HEAD..main` is 0.

Run here after the merge, serially, rc 0 unless said:
- tests/test_landing_goal.py: 12 passed.
- tests/test_why.py, tests/test_factory_manager.py and tests/test_queue_batch_item.py: 82 passed, 1 skipped (no
  Playwright in that run).
- `tests/test_factory.py::test_ergostat_check_on_the_factory_model_reports_no_new_finding`: passed.
- `uv run ruff check ergostat tests scripts dev/bin/measure.py dev/bin/landing.py`: clean.

Under Playwright 1.63.0 and the watchdog, rc 1 for both files:
- tests/test_queue_batch_item.py: 15 passed, 1 failed. The failure is
  `test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run`, the same 60 s timeout on `table.items tr.click`
  as in rounds 2 and 3, and it failed alone too. It is left alone for round 2's reasons (lesson 13).
- tests/test_items_page.py: 76 passed, 3 failed.
  - `test_every_surface_prints_the_servers_one_count_of_goals_off` fails on its own. It asserts the header
    `Loops · goals off …`, but main's goals-page-replaces-loops-page titles that page "Goals" (`pages.js:46`, main's
    line). This branch changes nothing there. It is main's test against main's page (lesson 13).
  - `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`: the same `#running` timeout as round 1,
    which failed there with the branch's changes taken out. It is left alone.
  - `test_the_graph_and_the_timeline_left_open_change_nothing`: it failed in the full file (mutations seen on a
    BUTTON and a SPAN) but passed alone with both of its parameters. That makes it a load-dependent failure on the
    graph and timeline pages. The branch's only page change is in the item page's why signature, which those pages
    never compute. I did not find whether the cause is a race in ergostat or the test's own timing (lesson 10).
    I am reporting it, not fixing it here.

Not run: the unit suite, the other two browser files, demo_check (no example touched).

### Round 5: main (278f54a4) merged, and the review's two findings

`dev/model/landing.yaml` conflicted in `goals:`. Main (switch-without-draining) removed `drains-within-bound` and its
`drain-overrun`. The branch had `main-moving` beside it. Main's removal is kept, and so is the branch's goal
(885bf854). Main's batch states (a `new` state first, and `batch.started` and `batch.run-started` written last) come
in unchanged. `git rev-list --count HEAD..main` is 0.

- **A landing that did not stand moved main** (`dev/bin/landing.py`, `landed_at`). A batch now counts as having moved
  main only when it ended `landed` or `partial` (`STOOD`). Those are the ends whose merges stayed on main and were
  pushed. A `pushing` batch (its push not settled), a `failed` one (its push denied: merges undone, gaps sent back,
  though the fold keeps `batch.landed`'s `landed` and `landed_at`) and a `given-back` one count for nothing in
  `main-still-minutes`, `main-stalled-minutes` or `gaps-landed-per-hour`. I chose not to count `pushing` because
  origin's main has not moved until the push runs. A push waiting on approval then reads as main still, which the
  reason already names ("landed N gap(s) and waits for its push to settle"). To count it, add one word to `STOOD`.
  New test `test_a_landing_that_did_not_stand_does_not_move_main`: a `failed` batch and a `pushing` one, each
  carrying `landed` and a later `landed_at`, leave main-still at batch/c-2's 420 minutes, landed-per-hour at 0.125,
  and the goal off at 312. The same batch as `partial` moves main (216).
- **The queue's head gap, moved on to `queued`, was not ahead** (`ergostat/why/within.py`). A batch now counts ahead
  of a waiting gap when it names an item of the gap's kind that waits in the gap's state (a leased one counted in
  the state it was taken from, as before) or that has left that state: a `from` of one of its moves is the waiting
  gap's state. That covers the real queue's path, approved, then leased, then queued (`queue.py take()`:
  `gap.queued`). Nothing in the rule names a kind (SPEC §5a updated). A gap that never was in the waiting gap's
  state still isn't counted, so a batch of a gap queued straight from elsewhere is not ahead of an approved one.
  The test now moves `gap/r` on to `queued` after its lease and reads the same "ahead of it: 1 unfinished batch
  item, the latest batch/r-6 (testing; size 1)". The test model's gap kind now begins in a `new` state, as the
  factory's begins in `open`. An item arrives in its kind's first state (`ergostat/spec/items.py:128`), and with
  `approved` first, `gap/q` had passed through approved on arrival.
- Seen to fail with the code broken: without the "has left its state" clause, the queued assertion fails (ahead is
  `{}`). Without the `STOOD` check, the denied-push test fails (216.0 == 420.0).

Docs: SPEC §5a (*place*), dev/README.md and `main-still-minutes`'s description in `dev/model/measures.yaml`.

Size: 112 net lines outside tests/, docs/ and dev/ (within.py 104, the why hooks 8, pages.js 0). Under 600.

Run here, serially, rc 0: tests/test_landing_goal.py (13 passed), tests/test_why.py with
tests/test_queue_batch_item.py and tests/test_factory_manager.py (82 passed, 1 skipped: the batch-item browser
test, without Playwright in that run), `tests/test_factory.py::test_ergostat_check_on_the_factory_model_reports_no_new_finding`
(passed), and `uv run ruff check ergostat tests scripts dev/bin/measure.py dev/bin/landing.py` (clean).
Not run this round: the browser files under Playwright (no page changed this round), the unit suite, demo_check (no
example touched). Bash refused a debug script (a Python heredoc reading an item's moves), so I found the
first-state arrival by reading `items.py` instead.

### Round 6: the review's finding (a batch ahead of every gap that ever left a state)

Main had not moved (`git rev-list --count HEAD..main` is 0), so there was nothing to merge.

- **"Ahead" was wider than a waiting gap's** (`ergostat/why/within.py`). Round 5 counted a batch ahead whenever its
  gap had ever moved out of the asking gap's state, so with any batch unfinished, every gap in an earlier state
  (open, planned, building, in-review, fix) read "ahead of it: N unfinished batch items". Now `waits_in` keeps, for
  each named item, only the `from` of its last take (its last move into `leased`), and drops it once the item moves
  back into that state. A batch counts ahead when its gap waits in the asker's state (a leased one in the state it was
  taken from, as before) or when its gap's last take was from the asker's state and it has not come back. The queue's
  head gap (approved, then leased, then queued) still counts ahead of an approved gap. A gap in `open` or `built` has
  none ahead, because the last take of a batch's gaps is the queue's take from approved: a gap the reviewer took from
  `built` was taken again later, from approved. Nothing in the rule names a kind. This reads the finding's first
  suggestion ("the from of its move into the lease"). I did not take its other suggestion (the state the gap was in
  when the holder named it), because that would compare the times of two items' events (lesson 2). If a gap's moves
  can't be read, it has no take, so it is counted by its state alone. That undercounts and invents nothing.
- New assertions in `test_a_waiting_gap_s_why_names_its_batch_and_run_or_the_batches_ahead`: a gap in `new` (the test
  model's first state, which `gap/r` left too) gets no `ahead` and no "ahead of it" in its summary while `batch/r-6`
  runs, and the approved `gap/later` still has it ahead. After `gap/r` goes back to approved, it is counted once, by
  its state, and the `new` gap still has nothing ahead.
- Seen to fail with the code broken: with round 5's "any state it left" clause put back next to the new one, the
  `new` gap's assertion fails (ahead `{'batch': {'n': 2, …}}`). Code restored, nothing of the experiment committed.
  Round 5's check (the queued assertion fails without the take clause) still holds, since that clause is what counts
  the queued head now.
- Docs: SPEC §5a (*place*). dev/README.md's line ("batches holding approved gaps are ahead of it") already says
  this, so it is unchanged.

Size: within.py +9 net this round, about 121 net lines outside tests/, docs/ and dev/. Under 600.

Run here, serially, rc 0: tests/test_landing_goal.py (13 passed), then tests/test_landing_goal.py,
tests/test_why.py and tests/test_queue_batch_item.py together (61 passed, 1 skipped: the batch-item browser test,
without Playwright in that run), and `uv run ruff check ergostat tests scripts dev/bin/measure.py dev/bin/landing.py`
(clean). Not run this round: the browser files under Playwright (no page changed), the unit suite, demo_check (no
example touched), and the `ergostat check` tests (no model file changed). Bash refused a Python heredoc that would
have rewritten within.py, so I made the same edits with the editor.
