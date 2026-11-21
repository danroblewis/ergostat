# planner-skips-continued: the planner never takes a gap that continues a branch

depends-on: []

Eight continued gaps on 2026-11-20 were leased by the planner before the intake fetched their branch: each cost a planner session and could have raced the intake. The instance has the fix as a local edit.

## Definition of done
The planner's `takes` in `dev/model/knowledge.yaml` has `where: {continues: null}`, so a continued gap waits for the intake.

## Files to touch
`dev/model/knowledge.yaml`, `tests/test_factory_knowledge.py`.

## Risks
- lesson-3: a continued gap whose branch cannot be fetched must still be said by the intake, never wait silently.

## Acceptance tests
- `tests/test_factory_knowledge.py::test_the_planner_never_takes_a_continued_gap`

## Size budget
5 net lines of code outside `tests/` and `docs/`.
