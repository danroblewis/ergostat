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
