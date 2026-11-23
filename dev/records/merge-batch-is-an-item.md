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

Round 2: the review's blocking finding. A run killed after its merges landed left its batch open forever. There were
three windows. First, while `running` has `landing`: recover() blocks and returns before abandoned(). Second, after
`running` is popped but before batches.pending() in ask(), so the push-main call too: recover() returns at once.
Third, one the review did not name: after pending() but before ask() saved the pending push, because pending() closed
the mark itself. Now:
- settled() writes what landed into run/batch.json (`outcome`, `back`, `failed`, `sha`).
- pending() marks the batch `pushing` and keeps it `open`. pushed(), which now takes `cfg` (the four queue.py calls
  pass it), closes the mark after saying the end.
- begin() first calls left(). It ends a mark still open with the outcome that mark says it landed (`landed` or
  `partial`, because its merges stayed on main). Its `why` says the run was killed after its merges landed, before
  its push was recorded.
- abandoned() skips a mark that is `pushing`, so a batch waiting on its push is still ended by its push.
- The choice made alone: the end is said with the outcome as landed on main, not `given-back`. Nothing was undone,
  and `gap.merged` was said for those gaps, or was being said. That holds even if the coordinator later undoes
  them while the queue is blocked. It is the most reversible choice: one line in left().
- A kill between pushed()'s event and its mark write says the end twice. That is better than never. It is not tested.
- New tests: `test_a_batch_killed_after_it_landed_ends_before_the_next_batch_begins` (in memory, the windows before
  and after pending(); the landing window leaves the same mark as before-pending), and
  `test_a_queue_run_killed_before_its_push_leaves_its_batch_ended_by_the_next` (a real queue run SIGKILLed in place of
  ask(), so between settled() and pending(), then the next gap's run). The test of a recovered run now also checks that
  a batch ended by its push is not ended again by the next begin().
- Seen to fail with the code broken: all three new cases with left() removed from begin(), and the recovery test with
  pushed() not closing the mark (said twice).
- dev/README.md says how a killed batch ends.

Run here, serially, with rc 0: tests/test_queue_batch_item.py (15 passed, 1 skipped without Playwright, and its browser
test passed under Playwright 1.63.0 and the watchdog), tests/test_queue.py (17), tests/test_queue_halves.py (55),
tests/test_queue_host.py (12), tests/test_factory.py::test_batch_of_one_is_todays_queue and
::test_a_green_batch_lands_every_gap, and `ruff check ergostat tests scripts`. Main had not moved (still 7a905955,
already merged). Not run here: the unit suite, the four browser files and the rest of tests/test_factory.py.
`ruff check dev/bin` reports B023 in dev/bin/plan.py and E501 in dev/bin/review.py. This branch did not touch those
files, and dev/bin/batches.py and dev/bin/queue.py are clean.

Fast suites, round 2 (`build` red again on `test_an_approved_switch_drains_and_switches_through_the_engine`: a
switcher run went past its 120 s bound). Measured here, serially, with a scratch test that was then deleted and never
committed: the test's two switcher runs took 43.6 s and 42.4 s, nearly all of it CPU (agent.ran: cpu 43.4 s of
43.4 s). With main's `dev/model/landing.yaml` and `ergostat.yaml` in its instance (the run showed main's model hash)
they took 44.2 s and 42.8 s. One `ergostat item --kind gap` call takes 0.86-0.92 s on either model. So the branch does
not make the switch test slower. What it adds is load beside it. The build runs `-n 8` on 4 CPUs (`suite_cpuset`),
and this branch's tests/test_queue_batch_item.py takes 200 CPU-s, mostly in the 7 tests that run the real queue. A
43 CPU-s run with a 120 s bound fails once it gets less than about a third of a CPU. The fix is in this gap's own file
only: those 7 tests are marked `serial` (conftest: run with nothing else of the run alongside), so they never run
beside the switch test. Its bound, the test itself, drain.py and conftest are unchanged. The cost is wall time late
in the build, while they run alone (about 3 minutes). To undo it, drop `@QUEUE`. Not proven: that the build is green
now, because the build cannot be run here. If the switch test still goes red, the load comes from main's own tests,
and the fix (drain.py's many `ergostat` calls, or `serial` on that test) belongs to a gap of its own (lesson 13).

Fast suites, round 3 (`build` red a third time on `test_an_approved_switch_drains_and_switches_through_the_engine`,
with the seven queue tests already serial). Found why this branch's build meets it: `[suites] build` is
`scripts/affected_tests.py`, which runs only the test files a branch changed, and this branch changes
tests/test_factory.py (the fixture's `batch.*` filter). So its build runs all of test_factory's ~195 tests under
`-n 8`, the switch test among them, which most branches' builds never do. The test's switcher runs are about 43 CPU-s
each, nearly all CPU, the same with main's model (round 2). That is neither a race nor a fixed sleep (lesson 10). It is
a CPU-bound run whose 120 s bound holds only on a quiet machine. The fix is CLAUDE.md's rule for that case: the test is
marked `@pytest.mark.serial` instead of `slow`. Its bound and its body are unchanged, and so are drain.py and conftest.
Left `slow`, it would start first and then idle its worker waiting for the lock. To undo it, put `slow` back. This is a
one-line change outside the Files list, in a file the branch already edits. This replaces round 2's "belongs to a gap
of its own": the branch's own diff is what puts the test in its build. Run here: the test alone (passed, 154 s) and
ruff (clean). Not proven: that the build is green now, because the build cannot be run here.

Round 3, merge of main (28ad5c4ad880). It conflicted in dev/bin/queue.py, where main added an outage handler
(`except Exception`: Docker or the AI service unreachable) right where the branch calls `batches.settled()`. Both
are kept. The handler now also ends the batch `given-back` with `why` "outage: <cause>" before its nack. Without
that line the `finally` would end it anyway, as "raised or stopped", because `batches.end()` keeps the first end
said. The line only gives it the truer reason. Run here, serially, with rc 0 after the merge:
tests/test_queue_batch_item.py (15 passed, 1 skipped without Playwright), tests/test_queue.py (17),
tests/test_queue_halves.py (55), tests/test_queue_host.py (12), tests/test_factory_outage.py (4), and
`ruff check ergostat tests scripts`. A shell `for` loop over the three queue files was refused, so each was run on its
own. Not run here: the unit suite, the four browser files, the rest of tests/test_factory.py, and the browser test
under Playwright since the merge.

Round 4: the review's blocking finding. The seven queue tests in tests/test_queue_batch_item.py were marked `serial`
only to keep them away from test_factory's switch test. That test has been `serial` itself since round 3, so it already
runs with nothing beside it, and these tests have no time bound of their own. Under CLAUDE.md they are `slow` (10 s+),
not `serial`. `QUEUE` is now `pytest.mark.slow`, and the module docstring says why. Round 2's reason for unmarking
them from `slow` (they started beside the switch test) no longer holds, for the same reason. There was nothing else in
the review. Main is still 8a27f9e3 and was already merged (71fbc4b2), so there was nothing to merge. Run here, serially, with rc 0:
tests/test_queue_batch_item.py (15 passed, 1 skipped without Playwright, 207 s) and
`ruff check ergostat tests scripts`. Not run here: the unit suite, the four browser files, the rest of
tests/test_factory.py and the browser test under Playwright. Only the mark and the docstring changed, so code
behaviour is the same as in round 3.
