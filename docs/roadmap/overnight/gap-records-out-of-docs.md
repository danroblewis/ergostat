# gap-records-out-of-docs: a gap's working record is written under dev/records/, not docs/

depends-on: []

The owner (2026-11-21) wants the per-gap working records out of `docs/`, which is for human readers. About 9,000 of the 10,000 doc lines landed by the first 51 gaps are these files in `docs/roadmap/overnight/`. They are not only logs: `dev/bin/fac.py` (`DEFS`), `intake.py`, `brief.py`, `review.py`, `implement.py` and `deps.py` read them as each gap's definition of done, and about 30 branches in flight carry their definition at the old path.

## Definition of done
1. A new gap's definition is committed at `dev/records/<branch>.md`, and everything that reads a definition finds it there.
2. A definition at `docs/roadmap/overnight/<branch>.md`, on main or on a gap's branch, and a `REF:docs/roadmap/overnight/X.md`, still resolve, so no gap in flight breaks. The new path wins when both exist.
3. The prompts, `dev/knowledge/house-rules.md` and `docs/roadmap/overnight/TEMPLATE.md`'s instructions name the new path.
4. Existing files are NOT moved in this gap. Moving them is a later, separate step once no branch in flight needs the old path.

## Files to touch
`dev/bin/fac.py`, `dev/bin/intake.py`, `dev/bin/brief.py`, `dev/bin/review.py`, `dev/bin/implement.py`, `dev/bin/deps.py`, `dev/knowledge/house-rules.md`, the prompts that name the path, `tests/test_factory.py`.

## Risks
- A branch in flight whose definition stops resolving would be sent back or parked: test both paths through the real readers, not a stand-in.
- `tests/test_factory.py` and `dev/bin/fac.py` are conflict-prone: keep the change small.

## Acceptance tests
- `tests/test_factory.py::test_a_new_definition_is_written_under_dev_records`
- `tests/test_factory.py::test_a_definition_at_the_old_path_still_resolves`
- `tests/test_factory.py::test_a_ref_to_the_old_path_still_resolves`
- `tests/test_factory.py::test_the_new_path_wins_when_both_exist`

## Size budget
40 net lines of code outside `tests/` and `docs/`.
