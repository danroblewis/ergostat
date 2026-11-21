# lesson-denied-settles: a denied lesson proposal is settled

depends-on: []

The goal `lessons-decided` has been off at 8 because the coordinator's 8 denied proposals stay `proposed`: a denial changes nothing on the lesson, so the goal can never hold and the librarian's loop looks unanswered.

## Definition of done
A denied `knowledge-change` moves its lesson to a settled state (`denied`, with who and why), which `lessons-decided` does not count. Existing denied proposals are settled by the same path. A denied shape is not proposed again from the same finding.

## Files to touch
`dev/bin/lesson.py`, `dev/bin/librarian.py`, `dev/model/knowledge.yaml`, `ergostat.yaml`, `tests/test_factory_knowledge.py`.

## Risks
- lesson-3: an action whose outcome cannot be read leaves the proposal open, never settled.

## Acceptance tests
- `tests/test_factory_knowledge.py::test_a_denied_lesson_is_settled_and_stops_counting`
- `tests/test_factory_knowledge.py::test_a_denied_shape_is_not_proposed_again`

## Size budget
50 net lines of code outside `tests/` and `docs/`.
