# plan-review: a plan lint before the review, the task graph in both briefs, a reviewer that reads the code

Branch `plan-review`, from origin/main at edf2248. 34 gaps sit in `replan` and 1 is building: the plan reviewer sent
back 30 of 30 plans in three hours. Its checklist is mechanical (lessons named, tests named, a plausible budget) and it
sees only the plan text and the lessons, not the code, so it nitpicks test design. The owner: "we don't want the plan
reviewer to spend its time reviewing things that a proper planning prompt can ensure ... Is it a simple check to make
sure that several things exist? Because that can be a simple rule or linting check."

## Definition of done

1. **A plan lint** (`plan.lint`, no AI), run by the program on each definition the planner writes, before it is
   planned, and again at the start of the plan review when the plan on disk is not the one linted (no session then).
   It finds: a missing `depends-on: [...]` line or `## Definition of done`, `## Files to touch`, `## Risks`,
   `## Acceptance tests`, `## Size budget` section; an acceptance test bullet with no `tests/...py::test_name`; a size
   budget with no number of net lines, or over `[gates] plan_budget_most` (600); a `lesson-N` under Risks that is no
   lesson of dev/knowledge/review-lessons.md; a `depends-on` name that is no gap (deps.resolver), no sub-gap of the
   same answer and no branch merged into main; a file to touch that is not on main and not marked new. A failure goes
   back to the planner with the findings (`gap.plan-sent-back`, `plan_sent_back_by: lint`) and does not count toward
   the plan kill rule; `plan_lint_failures` counts them, and the 6th parks (a planner that cannot write the format).
   The planner's other refused answers (a bad split, too many questions) are the lint's too.
2. **A task-graph brief** (`plan.graph`), given to the planner and the plan reviewer as `{graph}`: gaps merged in the
   last 3 days (title, branch, the files their merge changed, from the checkout), gaps active (leased, building,
   built, in-review, approved, queued, queue-failed, fix: title, branch, files to touch from their definition) and
   gaps ready or planned (the same, and depends_on). At most 40 lines; what does not fit is counted.
3. **The planner prompt** states the format once, as the lint checks it, and plans with the graph: never plan what
   landed, `depends-on` on active or planned gaps that touch the same code or that it needs, and one line under
   `## Relation to other work` on how it relates to overlapping work.
4. **The plan reviewer** is given a read-only clone of main and the reviewer's read-only tools (Read, Grep, Glob, git
   show/log/diff), and asks: can an implementor alone complete this well in its fix rounds, and is it the right thing
   to build now? It judges feasibility against the code, design soundness, fit with the graph and whether the tests
   would show done; formatting is the lint's. `fix` only for those; smaller points are `non_blocking`, appended to
   the definition as notes the implementor answers (the instance's local patch, kept); `park` only when it should not
   be built.
5. **Kill rule:** plan reviews park after `[gates] plan_kill_after` (default 4); lint failures never count.
6. **Model:** `plan-lint`, a program block drawn between the planner and the plan review (it lints any planned plan
   not yet linted, every 5m); flows `plans-failing-lint` and `plans-sent-back` told apart by `plan_sent_back_by`; the
   measure `plan-first-pass` (`plan.py yield`: of gaps whose first plan review is in the last 14 days, the share it
   approved) with the goal `plans-pass-first` (>= 0.5).

dev/README.md says so.

## Files to touch

- `dev/bin/plan.py`, `dev/prompts/planner.md`, `dev/prompts/plan_reviewer.md`, `dev/model/knowledge.yaml`
- `dev/bin/agents.py` (the plan reviewer's tools), `dev/bin/fac.py` (the stand-in planner's plan lint-clean),
  `dev/factory.toml` (`plan_kill_after`, `plan_budget_most`, the plan reviewer's session budget), `dev/README.md`
- `tests/test_factory_knowledge.py`

## Risks

- lesson-9: a lint test that passes on a good plan alone; each finding is shown by a plan missing exactly that piece.
- A plan held forever in replan by lint failures that cost a planner session each: bounded by the 6th lint failure.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_the_lint_catches_each_missing_piece`
- `tests/test_factory_knowledge.py::test_a_lint_failure_goes_back_uncounted`
- `tests/test_factory_knowledge.py::test_the_graph_brief_lists_merged_active_and_ready`
- `tests/test_factory_knowledge.py::test_the_graph_brief_stays_bounded`
- `tests/test_factory_knowledge.py::test_the_reviewer_sees_overlap_in_its_brief`
- `tests/test_factory_knowledge.py::test_non_blocking_notes_are_appended`
- `tests/test_factory_knowledge.py::test_the_plan_kill_rule_reads_the_setting`
- `tests/test_factory_knowledge.py::test_plan_first_pass_yield`
- the factory tests, the unit suite, ruff and `ergostat check`, rc 0.

## Size budget

300 net lines outside tests/ and docs/.
