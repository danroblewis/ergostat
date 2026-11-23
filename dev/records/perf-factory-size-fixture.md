# perf-factory-size-fixture: A script builds a factory-size state directory, so page speed and size can be tested without the live factory

depends-on: []

Problem: every measurement of owner item 2 was taken by hand on a copy of the live factory's state, and the live server (:8798) answered no API GET within 60-580 s for any explorer. Several gaps need 'a factory-size fixture' for acceptance (page budgets, answer sizes, forecast refresh, the estimates' cost), and none exists: tests/fixtures holds no state directory, and diagram-large-case-fixture saves only /api/graph JSON. The live record cannot be shipped (it holds the owner's work).
Change: a script scripts/factory_fixture.py (using scripts/scale_model's generator where it fits) writes a model and a seeded record into a directory given on the command line, deterministic for a seed, of a stated size matching the factory's measured shape: about 25 model files, 60 goals in 8 systems (two of them made by `use: modelling`), 260 sensors, 37 machine blocks, 8 item kinds with 1,500 items (one kind of 430 with depends_on chains, 40 of them paused, 10 dead), 30 sealed segments of events over 24 h, about 2,000 lease attempts with 60% uncounted give-backs on one gated block, and one goal with a planted off stretch of 20 minutes and one upkeep goal off. A pytest fixture `factory_state` builds it once per session into tmp (skipped under a `-m fast` run) and can start a page server on it. docs/roadmap or tests/README says what it holds and that live-factory numbers in a PR are taken on a copy by hand, not in CI.
Definition of done:
1. `uv run python scripts/factory_fixture.py OUT --seed 1` writes a state directory that `ergostat check` passes and whose counts match the sizes above (asserted by a test).
2. Two runs with one seed give byte-identical records.
3. A snapshot on it costs within a factor of two of the factory copy's (the PR gives both numbers).
4. The pytest fixture serves /api/status and /api/items from it.
Files: new scripts/factory_fixture.py, tests/conftest.py (the fixture), tests/test_factory_fixture.py, a README line.
Acceptance tests: the counts test, the determinism test, the served-answers test.
Budget: 180 net lines.

Milestone: pages-answer-fast. Owner items: 2. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 1 (2026-11-22). Built: scripts/factory_fixture.py (180 lines), the session fixture `factory_state` in
tests/conftest.py (with `serve()` and `project()`), tests/test_factory_fixture.py (the counts test, the determinism
test, the served-answers test, all marked slow), and tests/README.md. Done 1, 2 and 4 hold; 3 is half done (below).

- **1.** `test_its_sizes_match_the_factorys_measured_shape`: 25 files, 8 systems, 60 goals, 260 sensors, 37 machine
  blocks, 8 kinds, exactly; 1,500 items (gap 430, parked 40, dead 10, at least 250 gaps with `depends_on`); 30 sealed
  segments over the 24 h before `--end`; 2,061 lease attempts, 1,236 (60.0%) given back uncounted, every one at the
  gated block `gap-approved`, and none of the lease events refused by the fold; `gap-prompt` off for 20 minutes, read
  above its setpoint for those 20 readings; an upkeep goal off; and `ergostat check` exits 0.
- **2.** `test_one_seed_builds_a_byte_identical_record`: a second build with the same seed and `--end` gives the same
  sha256 for every file of the record (94 files: the segments, the head, the layout token, measurements.db), except
  `repo.json`, which names the model's own path. The segments' random names, the layout token and gzip's time stamp
  are taken from the seed while the script writes (patched in its own process only).
- **4.** `test_the_page_server_answers_status_and_items_from_it`: /api/status (the planted goal holding again, the
  upkeep goal off) and /api/items (430 gaps, 40 parked), both 200.
- **3, not done here:** the fixture's number is measured; the factory copy's is not, because the live factory's state
  is not in this container. On this fixture (Linux container, measured by a timing probe that was not committed, on
  the script one revision before the committed one: the same shape and sizes): `state.snapshot` (what /api/status
  answers from) 0.61 s cold and 0.29-0.32 s warm; the `ergostat snapshot` command (the HTML page in one file) 390 s;
  `ergostat check` 107 s; the record 101 MB. The coordinator should take the same three on a copy of the factory's
  state by hand and give both sets in the PR. If the factory copy's `state.snapshot` is far more than 0.6 s, the
  fixture is missing what makes the factory's slow (for example its transcript events, which it does not model).
- Breaks seen to fail (lesson 9): without the seeded uuid patch the determinism test fails (segment names differ);
  with the planted off stretch never ending, the served test fails (`gap-prompt` off); with the gated give-backs
  counted, the counts test fails (0 uncounted). A broken lease sequence would also fail the no-refusals check.

Decisions taken alone (the most reversible option each time):
- "Two of them made by `use: modelling`": `modelling` is a `once: true` template, so the second system comes from
  `use: upkeep` (needed anyway for "one upkeep goal off"). The factory itself has `modelling` and `interventions`.
- "Machine blocks" means declared blocks that are not `ai`, `person`, or ergostat's own `onoff`/`external`. The goals'
  generated `keep-*` onoff blocks would add 60 more. "8 item kinds" leaves out ergostat's own `ergostat.*` kinds,
  which the templates bring (10 of them).
- The record ends at `--end` (default 2026-11-22 00:00 UTC, so a run with no options is the same every time). The
  fixture passes the hour the session started, so pages read it as recent. "Paused" is the `messages: paused:`
  state `parked`, as in the factory. The filler that brings the record to 30 segments is the machine blocks' runs
  (`agent.started`/`agent.ran`), evenly over the day.
- "Skipped under a `-m fast` run": no `fast` marker exists, so the fixture skips when the `-m` expression mentions
  `fast`. A `-m fast` run selects none of these slow tests anyway. That skip was not run (named_tests.py takes no
  options).

Cost to the suites: the three tests take about 140 s serially (two builds of about 17 s each; `ergostat check` on
the record takes 107 s of that). Under xdist each worker that runs one of them builds its own copy (session scope is
per worker).

Not run here: the unit suite and the four browser files (left to the factory and the merge queue, as the rules say).
No page changed. main had not moved since the branch was made, so there was nothing to merge.

## Where it stopped

Parked by the factory (review/perf-factory-size-fixture-1, 2026-11-22 07:07).

Done 1, 2 and 4 are built with acceptance tests that can fail: the counts test (every size, read back from the model and record, no lease event refused by the fold, `ergostat check` exits 0), the determinism test (a second build in its own process, sha256 per record file) and the served-answers test (/api/status and /api/items from a real ThreadingHTTPServer). Done 3 is half done: the fixture's snapshot cost is measured, but the factory copy's is not, because the live factory's state is not in the implementor's container and cannot be shipped. The branch can't merge until the PR gives both numbers within a factor of two. Nothing in the gap's own code is wrong enough to block.

## Where it stopped

Round 2 (2026-11-23). This round had one finding: the work is done apart from readings from the live Mac or factory,
which belong to the coordinator and are not part of this gap. No code changed. main (7cb97857) is already merged into
the branch (02c924b8) and has not moved since, so there was nothing new to merge. On the merged branch, `uv run ruff
check ergostat tests scripts` is clean and `scripts/named_tests.py tests/test_factory_fixture.py` passes all 3 tests
(the counts test, the determinism test, the served-answers test) in 283 s, serially.

Readings the coordinator owes (done 3): on a copy of the live factory's state, taken by hand and not in CI, time
`state.snapshot` cold and warm, the `ergostat snapshot` command and `ergostat check`, and give the record's size. Put
them in the PR beside the fixture's numbers from round 1: 0.61 s cold, 0.29-0.32 s warm, 390 s, 107 s, 101 MB. Done 3
holds if the factory copy's `state.snapshot` is within a factor of two of the fixture's.

Not run here: the unit suite and the four browser files. Under the rules they are run by the factory and the merge
queue. No page changed.

## Where it stopped

Round 3 (2026-11-23). The two findings: the merge queue found this branch the first failing merge of a batch of 9 by
bisecting, and the unit suite failed with no test named. The queue's log is not in this clone, so the cause is
inferred, not seen. `fac.FAILED` matches `ERROR` lines as well as `FAILED`, so a fixture that failed at setup would
have been named. A unit run that names no test is most likely one killed whole: the watchdog (6 GB or 1,500 threads)
or the container's memory limit. This branch's tests are the heaviest in the suite. Under `-n 8`, `_slow_first` puts
each of the three on its own worker. Session scope is per worker, so each of those workers built its own ~100 MB
record at the same time, and the determinism test then built a fourth. The counts test also ran `ergostat check` (107
s) in the worker's own process, so its memory and module caches stayed with that worker. Changed (tests only; the
script is unchanged at 180 lines):
- `factory_state` is now built once a run. Under xdist the first worker to ask builds it in the run's temporary root
  (the parent of each worker's basetemp) while the others wait on a file lock. A failed build leaves no
  `factory-state.json`, so the next worker builds again in a fresh directory. The record's digests are taken as
  built and kept in that file, so files a later test writes into the shared record (`ergostat check`'s
  `extremes.json`, for one) cannot change what the determinism test compares. A parallel run now holds two copies
  (this one and the determinism test's), not up to four.
- The build runs with `ERGOSTAT_*` cleared (`clean_env`; the watchdog's tag is kept). A session fixture is set up
  before the autouse `home` fixture clears them, so when the suite ran as an engine's block, the build inherited
  that engine's `ERGOSTAT_SOCKET`, `ERGOSTAT_RUN` and the rest.
- The counts test runs `ergostat check` as `python -m ergostat` in its own process, with the same clean environment
  and a 900 s timeout. Its memory is freed when it ends.
- tests/README.md says it is built once a run.

Not proven: that this was the queue's failure. Without its log I cannot show that the old branch broke a limit, or
that this one stays under it. The shared build under xdist was not run either, because named_tests.py runs serially
and the whole parallel suite is the queue's to run. The serial path (the run's own basetemp) was run:
`scripts/named_tests.py tests/test_factory_fixture.py` passed 3 of 3 in 322 s, and the pre-change head passed 3 of 3
the same way. `uv run ruff check ergostat tests scripts` is clean. If the queue fails again with no test named, its
`suite_watch` line (`killed`, `peak`) says which limit was hit. If it was memory, the next reversible step is to mark
the three tests `serial`, so nothing else runs beside them. Done 3 still waits for the coordinator's readings on a
copy of the factory, as round 2 says. main had not moved since the merge at eab052ff, so there was nothing new to
merge.
