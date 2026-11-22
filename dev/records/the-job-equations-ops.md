# the-job-equations-ops: the-job's coupled rates written as equations, units consistent, check clean
depends-on: []

## Definition of done
- Every flow in `examples/the-job` whose rate is set by another rate (coflows, delays like `ramps-broke`, `actions-filed` from `postmortems`) has an `equation` with units; a cause that stays unmeasured is an exogenous auxiliary or a parameter with `estimate: true`, never a bare signed cause on a rate that has a known coupling.
- `ergostat check` on the-job reports no errors, no `equation-units`, no `units-mismatch`, and no other finding (the extreme-conditions run finishes).
- The architecture measures give the-job no notes: it joins the clean examples.
- Nothing in the world (`world/`) changes behaviour; parameters stay what that code implies.
- The README's "Where to look" says what the equations are, and claims nothing a test does not check.

## Relation to other work
- gap/diagram-lines-stay-attached, gap/diagram-frames-corners: they lay out examples; the-job's diagram fixtures (`tests/fixtures/layout_known.json`, `diagram_sizes.json`) are not edited here, and if a count moves the change is reported, not refitted.

## Files to touch
- `examples/the-job/job/incidents.yaml`
- `examples/the-job/job/safety.yaml`
- `examples/the-job/job/awareness.yaml`
- `examples/the-job/job/support.yaml`
- `examples/the-job/job/team.yaml`
- `examples/the-job/README.md`
- `tests/test_architecture.py`
- `tests/test_the_job_model.py` (new)

## Risks
- lesson-8: the README says "every rate is an equation" while some couplings stay signed causes; the claim must match the test's list.
- lesson-9: a check-clean test passing because problems are filtered by level; assert on codes, not only on errors.

## Acceptance tests
- `tests/test_the_job_model.py::test_check_reports_nothing_on_the_job`: `read` gives no problem of any level except those listed as record-dependent; fails if one equation is removed (verified by deleting `outages-noticed`'s equation).
- `tests/test_the_job_model.py::test_every_coupled_rate_has_a_units_consistent_equation`: each flow with an `instant` or delayed cause from another flow has an equation, and no `equation-units`/`units-mismatch` appears.
- `tests/test_architecture.py::test_the_clean_examples_have_no_architecture_notes_and_every_example_is_fast`: the-job is in `CLEAN`.

## Size budget
90 net lines
size: M (confidence: low)
