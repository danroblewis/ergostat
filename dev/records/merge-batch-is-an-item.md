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

## Where it stopped

Built, round 1. Main had not moved past this branch's base (the clone's `main` is 5411f137, this branch's parent), so
there was nothing to merge. The choices I made alone, each the most reversible I saw:

- **The event names.** A kind's `on:` maps each event type to one state, so one `batch.ended` cannot end in four
  states. The end is said as `batch.ended.<outcome>` (`.landed`, `.partial`, `.failed`, `.given-back`), with the
  outcome also in its data. To rename it, change the four `on:` lines and `batches._said()`.
- **One added event, `batch.run-started`.** The Timeline draws an item's bars from its state moves alone
  (`precedence._segments`), and a move needs a change of state. So each run starts with `batch.run-started` (to
  `testing`) and ends with `batch.run-finished` (to `isolating`: between the runs of a red batch). Each run is then a
  bar of its own without changing the shared renderer. A "run" is one round, as the definition's kinds say: `full`,
  `named` (the failing tests on each prefix), `halves` (both halves at once, one run). Rounds follow one another, so
  their bars never overlap. A clean batch spends a moment in `isolating` between its one green run and `batch.landed`.
  That is the price of not touching the renderer.
- **When a batch ends.** One that landed something is `pushing` until its push settles (`queue.settle()`: the push
  ran, was denied, or the coordinator settled it). A denied push ends it `failed`, because its merges are undone and
  its gaps sent back. With nothing landed it ends at once: `failed` if a gap was found failing, else `given-back`.
- **Counts.** `failed` and `passed` are summed over the pytest suites that printed a summary (`counted` names them).
  When none did, both read 0 with `counted: []`, which says the counts are unknown, not zero.
- **Outside the Files list.** `ergostat.yaml` (`messages: done` for `batch`, so its finished states are declared, not
  guessed from the record), `dev/README.md` (the paragraph on batch items), and `tests/test_factory.py` (its fixture
  keeps `batch.*` events out of the event lists about 50 queue tests compare exactly, as it already does for
  `session.*`; they still fold into its record).
- **More than asked.** A run killed part way (SIGKILL) would leave its batch `testing` forever. `recover()`, which
  already puts main back in that case, now ends the batch `given-back` (`batches.abandoned()`, read from
  `run/batch.json`).

Size: 0 net lines outside tests/, docs/ and dev/ (the one `ergostat.yaml` line is a change, not an addition).
batches.py is 239 lines and the queue.py hooks are 21 net (28 added, 7 removed), both under dev/.

Run here, serially, with rc 0: tests/test_queue_batch_item.py (13 passed, its browser test under Playwright 1.63.0
and the watchdog), tests/test_queue.py (17), tests/test_queue_halves.py (55), tests/test_queue_host.py (12), and ruff.
Not run here: the whole unit suite, the four browser files and the rest of tests/test_factory.py, whose fixture changed
(the queue runs them). Seen to fail with the code broken: the failing-write test with begin() unguarded, and the
Timeline test with `batch.run-finished` moving to `testing` (one bar, not three). The browser test is not mutated
separately: it checks the same bars as drawn. Without Playwright, as in the unit suite, it skips, as
tests/test_export.py's do.

Renamed after `ergostat check` (round 1, `event-names-mixed items.batch`): the four end events are now
`batch.ended-<outcome>` (`batch.ended-landed`, `-partial`, `-failed`, `-given-back`), not `batch.ended.<outcome>`.
The check reads an event as the kind, a dot, then a past-tense verb, so `batch.ended.landed` had the head
`batch.ended` and was flagged. The bullet on event names above should read with that change. The finding is fixed in
the model, not allowed: the definition has no `allows-findings` line.

Fast suites, round 1 (`build` red on two tests of tests/test_factory.py):
- `test_batch_of_one_is_todays_queue` asserted that gap/a's queue run says nothing of any item but gap/a. That run
  now also speaks for its own batch item, the point of this gap. The test still holds everything else to gap/a, and
  now also asserts that the `batch.*` events name exactly one item, gap/a's batch (`batch/a-...`). It passes alone.
- `test_an_approved_switch_drains_and_switches_through_the_engine` passed alone here (145 s), but under `-n 8` a
  switcher run outlived its 120 s bound. Its bounds are unchanged. The likely cause, not proven: this branch's six queue
  tests were marked `slow`, so `conftest._slow_first` started them all first, one per worker, beside the switch test.
  On main, three slow tests started at once. The six are now unmarked and run later, as stolen work. Main's timing
  could not be measured: `git worktree add -q /tmp/mainwt main` and `git checkout main -- dev/model/landing.yaml
  ergostat.yaml` were refused. If it goes red again, compare it with main's in the same slot.
