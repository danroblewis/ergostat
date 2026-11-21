# knowledge-queue: knowledge has its own work queue, and no longer goes through the gap queue

depends-on: []

The owner (2026-11-21): "i dont think these workers are supposed to build the knowledge base, especially not as separate tickets... we can have multiple ticket queues and multiple types of workers, each with their own work cycles. this work queue in particular is about closing gaps."

Today an approved lesson makes a `gap/knowledge-*` (`dev/bin/lesson.py request`): a full Opus implementor, a review and a merge to add a few lines to `dev/knowledge/review-lessons.md`. The `lesson` item kind already exists and is the natural queue.

## Definition of done
- **The queue:** a `lesson` item moves proposed -> approved -> `applied` (or `denied`, `retired`). Its exact text lives on the item. An approved `knowledge-change` applies it through a small program worker with its own block in `dev/model/knowledge.yaml`. No session, branch, review or merge queue, and it never creates a gap. `lesson.py add` and `retire` take the same path.
- **Briefs carry it:** `knowledge.block` gives implementors, reviewers and the pipeline manager the files' lessons plus the applied items, a "seen as" line under its lesson and a new lesson as its own entry, within the existing size budget, with ids recorded as carried today. A retired item stops being carried. `knowledge.py sync` shows applied entries as `knowledge/*` items.
- **It survives upgrades:** applied items live in the instance's record, so a switch keeps them. The repository's knowledge files stay as the seed.
- **Migration, once and idempotent:** each lesson in state `requested` whose `gap/knowledge-*` has not merged becomes `applied`, and that gap is closed with the reason. A gap merged already is left alone and its lesson is not carried twice. Named by that link only: no other gap is touched, and `gap/kb-*` is out of scope.
- **Measured:** lessons waiting and time from proposed to applied, with a goal read by the worker's loop. `dev/README.md` describes the queue.

## Files to touch
`dev/bin/lesson.py`, `dev/bin/knowledge.py`, `dev/bin/librarian.py`, `dev/model/knowledge.yaml`, `ergostat.yaml`, `dev/README.md`, `tests/test_factory_knowledge.py`.

## Risks
- lesson-1: two workers applying one approval record it once.
- lesson-3: an unreadable record leaves the lesson unapplied, and a brief says it could not read them rather than silently carrying none.
- lesson-9: tests go through the real action and the real brief, not a stand-in for either.

## Acceptance tests
- `tests/test_factory_knowledge.py::test_an_approved_lesson_is_applied_with_no_gap`
- `tests/test_factory_knowledge.py::test_the_next_brief_carries_an_applied_lesson`
- `tests/test_factory_knowledge.py::test_a_retired_lesson_stops_being_carried`
- `tests/test_factory_knowledge.py::test_applied_lessons_survive_a_version_switch`
- `tests/test_factory_knowledge.py::test_the_migration_is_idempotent_and_touches_only_linked_gaps`
- `tests/test_factory_knowledge.py::test_a_merged_lesson_is_not_carried_twice`

## Size budget
150 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: every point of the definition, with the six acceptance tests passing. The net count outside `tests/`
and `docs/` is 153: 94 lines of Python, 38 of model YAML and 20 of README prose. The code alone is inside the budget,
and the queue's own core count (which leaves out `dev/` and the root model) is 0. No headless reviewer was there to ask,
so I took these choices, each the most reversible one:
- The action keeps its command, `lesson.py request {lesson}`, so an action held from before still runs. It now records
  `lesson.approved` with the exact text (`entry`) and never makes a gap.
- The migration runs inside `lesson.py settle` (block lesson-settle, every 10m), idempotent, rather than as a one-off
  command. A `gap/knowledge-*` in flight (building to queue-failed) is left for a later run, never closed under a
  running session. Its gap is closed with `end: superseded`.
- A new lesson from the librarian has no check: its text says the check is "not yet written". The coordinator
  retires it and `add`s it again with one. Numbers go past the seed's and every applied one's, so a later seed lesson
  numbered the same would collide. No gap writes the seed any more, so I left that unhandled.
- lesson-1: the lease (pool 1, fenced) is the lock. The run also reads the item again and applies nothing unless it is
  still `approved`, which is tested.
- knowledge-sync no longer sets `flow.lessons-added`; lesson-apply does, since one flow has one actuator.

After the fast suites failed (the unit tail showed only uv's build lines, so it did not name the failing test): this
session had no shell, so I could not run a test, see the failure, or commit. Reading the code, I found a real bug:
under the block's lease the item is `leased` (its lease's `back` is `approved`), so `apply`'s re-read never saw
`approved` and a live run applied nothing. The fake record never showed this. `apply` now also accepts `leased` with
`back: approved`, and the first acceptance test covers both cases (leased from approved: applied; leased from another
state: nothing). Neither this edit nor the test has been run or committed. Next: commit, then run
`tests/test_factory_knowledge.py` and `tests/test_factory.py` one at a time to find the unit failure, if it is
something else.

Round 2 (answering review/knowledge-queue-1, every finding):
- IN_FLIGHT omitted `leased` (blocking): the migration now uses an allowlist, `QUIET` (open, planned, replan, ready,
  fix, parked, closed). A gap in any other state, or one whose `lease.holder` is set, is left for a later run. For
  ready/fix, which a block can take between the read and the close, the migration reads the gap again after
  `gap.closed`. If the lease fence moved, the lesson stays `requested`: if that run then merges the gap, the file
  carries the lesson and the record does not. This is detection after the write, not a lock, because the record has
  no conditional write. The cost is a gap closed under a run that had just taken it; its lesson is never carried
  twice. The test covers a leased gap, a ready gap held by a lease, and a lease taken as the close is written (the
  fake's `take_on_close`).
- A seed/record number clash (blocking): `number()` keeps one number for each new lesson (`kind: entry`) still
  `requested` as a gap that has not merged or closed (a gap not in the record counts as open: lesson-3). Each such
  gap numbers itself next in the file when it merges. `knowledge.applied()` also catches a clash that happens
  anyway: the record's entry is carried as `lesson-N-record` and stderr says so, so no heading or sync item appears
  twice. Not handled: `retire N` still retires both sides of such a clash. With the reservation it should not
  happen. New test: `test_a_new_lesson_never_takes_a_number_the_seed_will`.
- number() in two programs with no shared lock: the migration no longer numbers or applies. It records
  `lesson.approved` (with `migrated_from`), and only lesson-apply (pool 1, under its lease) numbers. Tests apply each
  migrated lesson through the real `lesson.py apply` run.
- gap/knowledge-retire-N gaps without a `lesson.requested` link: left as they are, as the definition says ("named by
  that link only"). The owner may want to close them by hand (`backlog.py`) rather than have an implementor build them.
- Mutation checks (lesson-9), each run and failing as expected: no lease-holder check, `leased` made closable, no
  fence re-read after the close, no reservation, no clash check.
- Size: net lines outside `tests/` and `docs/` are now 167 (238 added, 71 removed), 17 over 150. Answering the two
  blocking findings added about 14 lines: the reservation, the clash check and the fence re-read. Under this round's
  brief, which also leaves out `dev/`, the count is 0. The overrun is these fixes, not new scope.
- Run: `tests/test_factory_knowledge.py` (68 passed), `tests/test_factory.py` (91 passed, 2 skipped), ruff clean.
  Main has no commits past this branch. The four browser files and the whole unit suite were not run here: the
  factory runs them.
