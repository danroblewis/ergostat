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

## Where it stopped
Built; nothing is left. This note gives the reason for going over the budget and a file outside the list.
- 6 net lines outside `tests/` and `docs/`, one over: 1 in `dev/model/knowledge.yaml` and 5 in `dev/bin/intake.py`.
  The intake lines answer the lesson-3 risk. With the planner no longer taking continued gaps, two cases would have
  sat open with nothing said: a fetch into the drop that fails (before this, `continued()` returned False silently),
  and a fetched branch with no definition of done on it (before this, the planner would have planned it). The intake
  now says each one on stderr, as it already did for a branch the checkout lacks. This is the most reversible option:
  messages only, and no state changes.
- No origin remote in this clone, so there was no origin/main to merge. Local `main` is already an ancestor of the
  branch.
