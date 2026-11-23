# plan-routes-unbuildable-done-items: a definition of done whose items need what the implementor's container cannot do (a server on a port, screenshots looked at by a person, CORR_SHOTS-style env on a command, Docker --sandbox or macOS, input files not in the repository) is marked at plan time, and those items become a measure-runs request or an owner need before the gap is built
depends-on: []
## Definition of done
1. dev/bin/plan.py classifies each done item against an allowlist of what an implementor session can run (pytest under suite_watch, ruff, demo_check, git); any item outside it is marked `needs: owner|measure` in the definition with the reason.
2. A gap whose definition has such an item is not leased to an implementor until that item is either a measure-runs request that the gap's tests can satisfy, or an owner need answered (needs park before building, not after a review).
3. The velocity record counts the parks caused by such items (`env-parks`) beside first-pass-yield.
4. SPEC and dev/README (The pipeline manager) say so.
## Acceptance tests
- tests/test_plan.py::test_a_done_item_needing_a_port_server_is_marked_needs_measure
- tests/test_plan.py::test_a_done_item_needing_files_outside_the_repo_is_a_needs_park_before_building
- tests/test_plan.py::test_a_plain_pytest_done_item_is_not_marked
- tests/test_measure.py::test_env_parks_are_counted_and_left_out_of_first_pass_failures_they_caused
Each is broken (classifier returns buildable for all) and seen to fail.
## Size budget
180 net lines outside tests and docs.

## Where it stopped

Built, round 1: items 1-3 and dev/README's half of item 4. About 114 net lines in dev/bin (128 added, 14 removed),
within the 180.

Not done: docs/SPEC.md. SPEC describes ergostat itself and never the factory: it has no mention of the implementor,
plan.py, the pipeline, or dev/README. A factory section in the product spec would be the first. Leaving it out is
the more reversible choice, so the text is in dev/README instead (*Plans, research and what the factory knows*:
"Done items the implementor cannot do"; *The pipeline manager*: measure-runs and the velocity record). The owner
decides whether SPEC should carry it.

Choices made without anyone to ask (each easy to undo):
- The allowlist is applied to backticked spans that read as commands. A span counts as a command when it starts
  with a known program name (uv, python, git, npm, docker, ergostat, ...) or is a script path with arguments.
  Prose is checked against a pattern list of needs (a port, an env variable, screenshots by a person,
  Docker/--sandbox/macOS/seatbelt, files outside the repo). Wording outside both is not caught, and dev/README says
  so.
- A command off the allowlist, a port server and an env variable are `measure` needs. They become owner needs when the
  definition names no acceptance test a measure-runs request could run.
- An owner need parks the gap in the same event that records its definition, so it is never ready and never leased.
  `parks.py resume` readies it again as itself once `gap.need-met` is recorded. `manage.py continue` refuses such a
  park, since there is no branch to continue.
- Readying again records `gap.defined` with the gap's original `defined_by`. So knowledge.yaml's "entering ready by
  defined_by" flows count that gap a second time. The model is unchanged.
- `env-parks` counts the plan-time parks (`env_parked_at`, which a later park keeps) plus every review whose verdict
  parked a marked gap (`env_needs`) for a need. `first-pass-yield` leaves out those first reviews.
- A definition the coordinator wrote before planning, which the intake readies, is not classified. The planner's own
  path, the S path, splits, the lint sweep, and a coordinator file that lands while the planner runs are classified.
