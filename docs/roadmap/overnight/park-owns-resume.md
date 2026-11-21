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

## Where it stopped

Built in full, round 1: nothing is left that this definition asks for. Nobody was there to ask, so the implementor
made these choices, each the most reversible one it saw:

- **Who parks for which kind.** The implementor's kill rule, the reviewer's kill rule and its last-attempt failure,
  the queue's conflict, triage, the plan lint and dead letters all park as `kill-rule`. The pipeline manager's
  approved `manager-park` is `deferred`, and the plan review's approved `park-gap` is `cancelled`. Split-watch parks
  as `split` and names the stopped sub-gaps. A reviewer's park that gives no kind, an unknown kind, or a `waits_on` /
  `needs` naming nothing checkable counts as `defect`. That is the worst case: the manager looks at it, so it never
  waits silently.
- **One resumer, on the parkers' behalf.** One program block, `park-resume` (`dev/bin/parks.py resume`, every 5
  minutes, no AI), resumes every park of a kind a program resumes. It does this for whoever parked it, rather than each
  parker carrying its own loop. It records `resumed_by: park-resume` and the condition that cleared. A resume is not
  an intervention, because it is the loop.
- **`needs` is cleared by an event** on the parked gap, `gap.need-met`, with a `need_met` field that says what was
  done. Any value clears it; the value is not matched against the named action. A new park clears `need_met`,
  `resumed_as` and `resumed_at`, so an old one never applies to a later park of the same id (lesson 5).
- **A split is resumed differently.** It does not get a `continues` gap: a split gap has no branch of its own. It goes
  back to `split`, so the join can move it on. Each stopped sub-gap stops being its child, so split-watch does not
  park it again, and each sub-gap's continuation becomes its child.
- **A continue by hand also records `gap.resumed`.** So the program never resumes a park twice: `continue_gap`
  re-reads the park under `run/continue.lock` and refuses one already resumed. A continue by hand still works on one
  resumed already, as before.
- **The watch.** The `parked` situation is now raised only for kinds no program resumes (`defect`, `kill-rule`, or no
  kind given). A new `waiting` situation is raised for a `waits_on` / `needs` park not cleared within
  `[manager] park_wait_hours` (24), once per park.
- **Measures.** `measure.py parks|resumes|parked-hours KIND` reads any kind. Each measure counts a gap's last park
  only. The model declares sensors for four kinds' parks (`waits_on`, `needs`, `defect`, `kill-rule`) and for the
  resumes and hours of `waits_on` and `needs`, not all 21 combinations. The Items page shows `parked_for` (the gap
  kind's `show`).

Not verified: `ergostat check`'s warnings on the new model entries could not be run in this session (only pytest
and ruff were allowed). `test_the_factory_model_loads` passes, so the model has no errors. The race between a
continue by hand and the resumer has no test: the lock is there, but no test puts a competing write between the read
and the write.
