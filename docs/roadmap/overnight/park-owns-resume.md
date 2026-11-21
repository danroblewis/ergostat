# park-owns-resume: whoever parks a gap says what it waits for, and resumes it when that clears

depends-on: []

The owner (2026-11-20): "If the work is done, and they were parked, who parked them? Because it would be the
responsibility of that agent or process to unpark them, right?" Tonight about a dozen gaps were parked by the reviewer
with their work done — parked on a condition outside the gap (the branch carried another gap's unlanded merge; a
measurement only the coordinator could take; the old kill rule) — and nothing resumed them when the condition cleared.
A park was a dead end for the process that made it.

## Definition of done

- Every park says **why, as a kind, and what would end it**: `parked_for` one of `defect` (the gap's own work is wrong:
  findings), `waits_on` (a gap or branch named, e.g. the unlanded merge it carries), `needs` (an action named for someone:
  a measurement, an approval, with who), `kill-rule` (rounds or hours ran out), `deferred` / `cancelled` (the
  coordinator's), `split` (a sub-gap stopped). The reviewer's park verdict gives the kind and the condition (its prompt
  asks for it; a park with work done but an outside cause is `waits_on`/`needs`, never `defect`); the queue, the kill
  rule, split-watch and dead-letters set theirs.
- **The parker resumes what it parked** when the condition clears, by a program (no AI): `waits_on` when the named gap
  merges (or the named commits are on main), `needs` when the named action is recorded done (an event the coordinator or
  owner adds), `split` when the stopped sub-gap is resumed or closed. Resuming is a `continues` gap, as by hand. Each
  resume is an event with the condition that cleared. `kill-rule` and `defect` are never resumed by the program: they go
  to the pipeline manager (its park situations), which may resume with more rounds when the findings are fixable.
- The watch raises a situation for a `waits_on`/`needs` park whose condition has not cleared in N hours (a setting), so
  nothing waits silently.
- Measures: parks by kind, resumes by kind, time parked by kind; the Items page's park reason shows the kind.

## Acceptance tests

- `tests/test_factory.py::test_a_park_waiting_on_a_gap_is_resumed_when_it_merges`
- `tests/test_factory.py::test_a_park_needing_an_action_is_resumed_when_it_is_recorded`
- `tests/test_factory.py::test_a_defect_park_is_never_resumed_by_the_program`
- `tests/test_factory.py::test_a_waiting_park_past_its_hours_raises_a_situation`

## Size budget

220 net lines of code outside `tests/` and `docs/`.
