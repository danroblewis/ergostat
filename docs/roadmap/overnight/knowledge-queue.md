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
