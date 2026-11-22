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

## Where it stopped
Built, round 1. Before the change `check` gave the-job no error, no `equation-units` and no `units-mismatch`; four
of the six coupled rates already had equations. What changed, and the choices made with nobody to ask (each the most
reversible one):
- `actions-filed` (incidents) now has `auxiliary.actions-per-postmortem * flow.postmortems`. The ratio stays an
  exogenous auxiliary, valued by a new parameter `actions-each` (2.5, range [2, 3]: `randint(2, 3)` in
  world/traffic.py). This follows software-factory's `ops-broken-per-ticket`. Making the ratio a parameter instead
  took a part out of incidents and gave it a `system-splits` note (modularity 0.46), so the-job could not join `CLEAN`.
- `docs-needed` (documents) is also a rate set by another rate (`instant` from `docs-approved`), so done item 1 covers
  it, although `documents.yaml` is not in the Files list. It now has `workdays-per-hour * changes-base +
  next-docs-per-approval * flow.docs-approved`, with `changes-base` 0.35 docs/workday (`RATES["change"]`,
  `estimate: true`) and `next-docs-per-approval` 0.75 (three of the four stages' approvals open a next document).
- The one problem at level `finding`, `missing-feedback` on `notes-reach-work` (messages.yaml, not in the Files
  list), is answered with a person block, `route-notes` (agent `me`, out `flow.messages-routed-by-hand`). That is how
  the model already says "only I can". As a result the-job's status no longer has a goal no controller holds, which
  `tests/test_graph_cli_web.py::test_the_status_says_the_models_purpose_its_systems_and_its_controlled_goals` needed
  (`controlled < loops`). That test now removes the block in its own copy of the model, so its strict check stays.
- "record-dependent": `read` on the-job gives no problem that depends on a record. What is left are 98 notes,
  allowed by code in `LEFT` in the test: `no-description` (60), `collector-undescribed` (17), `no-equation` (15: the
  decision rules of flows a block moves, none of them a coupled rate, which the test also asserts),
  `event-names-mixed` (3), `schedule-removed` (2) and `queue-goal-tolerance` (1: `ci-upgrade-planned` holds `<= 1` on
  purpose). These are left: answering them means descriptions across every domain file and decision rules for the
  block-moved flows, both outside this gap's couplings and its budget. Any `finding` or `error`, and any other note
  code, fails the test.
- The two coupled flows of ergostat's `modelling` template (`model-mended`, `requests-answered`) are left out of
  `COUPLED` (`template_made`). Changing the template would change every model that uses it.
- Seen to fail (lesson-9): with `outages-noticed`'s equation removed, both new tests fail (`units-mismatch`,
  `parameter-unused`; no equation). With `actions-filed`'s equation removed, only the coupled-rate test fails: `check`
  itself does not flag a coflow that has an auxiliary ratio but no equation.
- Diagram fixtures not edited; `test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time[the-job]` passes
  as recorded.
- Not run: `scripts/demo_check.py` (the command `uv run python scripts/demo_check.py --help` was refused here), the
  full unit suite and the four browser files (left to the factory).
