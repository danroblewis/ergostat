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

## Where it stopped

Built: 34 net lines, inside the budget. Here is what was decided with nobody to ask; each choice is the easiest to undo:

- **The path.** `lesson.py settle` reads every denied `ergostat.action` item. For each `knowledge-change` whose
  `args.lesson` is still `proposed`, it records `lesson.denied` on that lesson with `denied_by`, `why` (the
  denial's note) and `action`. A program block, `lesson-settle` (`dev/model/knowledge.yaml`), runs it every 10m. It is
  not triggered by the denial event, so the 8 proposals already denied are settled by that same sweep the first time
  it runs. It also needs nothing new from the librarian.
- **A denial by the gate is not a decision.** A denial by `gate` (fencing, when a lease is over) leaves the lesson
  `proposed`. program.py asks for such an action again in any case.
- **lesson-3.** If the record cannot be read, `fac.items` raises and the sweep stops with nothing written (tested).
- **lesson-1.** The sweep reads "proposed", then writes "denied", with no lock held between. The only other writer
  that moves a proposed lesson is `lesson.py request`, which runs only from an approved `knowledge-change` of the same
  lesson. An owner's denial is final on its action (§12r: a later approval is ignored), and `known()` in
  `ergostat/actions/program.py` gives the denied action back for the same key, so no second action is made. That is
  an argument from the code, not a test that forces the race. `lesson.py request` also refuses a lesson that is not
  `proposed` (tested on a denied one).
- **Not proposed again.** The librarian already proposes only an id that is not known (a new shape) or one still
  `seen` (a new class). A denied lesson keeps its id and its state, so this branch changes only its docstring. The
  test fails if the guard lets a denied id through (checked by mutation).
- **Not done.** `origin/main` was not merged in: this clone has no `origin` remote and a fetch was refused. Only
  `tests/test_factory_knowledge.py` was run (51 passed) and ruff (clean). The unit suite and the browser files were
  left to the factory. `dev/knowledge/README.md` (the librarian's loop) does not yet say that a denial settles a lesson.
  That file is not in this gap's files.
