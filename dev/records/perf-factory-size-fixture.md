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
