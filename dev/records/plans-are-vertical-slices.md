# plans-are-vertical-slices: Planners split work into thin end-to-end slices

Teach the planner and definition prompts to split a feature into vertical slices: each slice works end to end and lands on its own, instead of layers that only work together. Add an example from a recent feature.
Done: 1. The prompts say it, with the example. 2. A planner test on a fixture feature produces slices that each have their own acceptance test.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1: built. About 50 net lines outside tests and docs (dev/bin/plan.py, dev/factory.toml, the two prompts,
dev/README.md).

1. The prompts say it, with the example. `dev/prompts/planner.md` has a section "Split into vertical slices": each
   sub-gap works end to end and lands on its own, never split by layer, and each slice has acceptance tests of its own.
   Its example is the Agent page, which was built as layers (`agent-spec-api`, then `agent-show-page`, then
   `agent-names-link-to-their-page`). The prompt sets that against the same feature cut into slices (ai prompt, then
   rule law, then program, then links). The format's Acceptance tests point says a test named by two sub-gaps may send
   the split back. `dev/prompts/definition.md` (the template for definitions the coordinator and the pipeline manager
   write) says the same in its Definition of done paragraph and its test bullet, with the same example.
2. A planner test on a fixture feature. `tests/test_plan.py::test_a_planned_split_is_vertical_slices_each_with_its_own_test`
   runs plan.py with a stand-in planner on a fixture feature (an Agent page). The layered split, where the api and the
   page share one test, is sent back with a finding that names the test and both sub-gaps, and no sub-gap is made. The
   sliced split is accepted. Each of its three sub-gaps is ready, and the definition file of each names its own tests:
   four tests in all, none of them shared.
   `tests/test_plan.py::test_own_tests_is_off_unless_declared_and_refuses_a_value_not_true_or_false` covers the option.
   Each test was seen to fail with the code it guards broken: the rule taken out for the first, the rule always on for
   the second.

Decisions taken without the owner, each easy to undo:
- The rule check is `[plan] own_tests`, off unless declared, following the owner's decision that general parts are
  options. `dev/factory.toml` declares it `false`, because the session does not change the live instance. The
  coordinator turns it on with one line. Turning it on unconditionally would also have changed today's split tests,
  which share one test name across sub-gaps.
- A value that is not true or false (`"yes"`, `1`) stops the planner before any session. It is not read as on or off
  (lesson-3).
- The rule checks that sub-gaps do not share a test. It cannot check that each test really runs end to end, and
  dev/README.md says so (lesson-8). That half rests on the prompt.
- The record has no `## Entry` section, and none was added, because this file may only gain "Where it stopped". If
  the gap needs a GAPS.md entry, the coordinator adds it.

Tests run: tests/test_plan.py (6 passed), tests/test_factory_knowledge.py and tests/test_gapsdoc.py (151 passed). Ruff
on ergostat, tests and scripts is clean. `ruff check dev/bin` reports two findings on lines this branch did not touch:
B023 at plan.py's join_brief and E501 at review.py:47. Not run here: the full unit suite and the four browser files
(no page changed). Main has not moved since the branch was cut, so no merge was needed.
