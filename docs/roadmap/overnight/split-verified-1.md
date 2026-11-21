# split-verified-1: a split's sub-gaps sized and covering the parent, the coverage given to each sub-gap's plan review
depends-on: []

## Definition of done
- **Sub-gaps sized.** `plan.py` sends back a split when a sub-gap's `## Size budget` has more than 250 net lines, or no number of net lines it can read (missing or unreadable counts as over). Like every unusable answer, it goes back to the planner and counts toward the lint-failure park, and the finding names the sub-gap. A budget of exactly 250 is accepted. A single definition keeps today's rule (`[gates] plan_budget_most`); sizing single plans is gap/plan-by-size's work. The 250 is a named constant in `plan.py`, not a config number.
- **Coverage block.** A planner's split answer must contain exactly one `<coverage>…</coverage>` block. It restates what the parent must do, one point per `- ` line, and each point ends with `(by: name, name)` listing the sub-gaps that build it. `plan.py` sends the split back, naming the problem, when:
  - there is no coverage block, or more than one;
  - a point has no `(by: …)`, or its list is empty;
  - a name in a `(by: …)` is not one of this split's sub-gaps;
  - a sub-gap is named by no point.
  
  A single-definition answer needs no coverage block, and one that has a block is not refused for it.
- **Saved as the parent's plan.** When a split is accepted, its coverage block is written to `run/plans/<parent-branch>.md`. It replaces any file left by an earlier split of the same parent, so a replanned parent never keeps its old coverage. Nothing is written when the split is refused. The parent stays in `split`, and the `plan.py lint` sweep never turns that file into a definition.
- **Plan review sees it.** When a sub-gap gets its plan review (`planreview.py`), the brief includes its parent's coverage from that file, under a heading saying it is the parent's coverage and which sub-gap this review covers. A gap with no parent, or whose parent has no coverage file, gets `(none)` and the review still runs.
- `dev/prompts/planner.md` tells the planner about the coverage block and its format and about the 250-line limit per sub-gap. `dev/prompts/plan_reviewer.md` has the coverage placeholder. `dev/README.md`'s planner paragraph describes both checks.

## Relation to other work
- gap/split-verified-2: builds on this; the join judge reads the coverage saved here at `run/plans/<parent-branch>.md`.
- gap/split-verified-3: builds on this; split quality is measured on splits that passed these checks.
- gap/kb-proposals: avoids its files (it touches `dev/bin/fac.py`; this change does not).

## Files to touch
- `dev/bin/plan.py`
- `dev/bin/planreview.py`
- `dev/prompts/planner.md`
- `dev/prompts/plan_reviewer.md`
- `dev/README.md`
- `tests/test_factory_knowledge.py`

## Risks
- lesson-3: a sub-gap budget that cannot be read (no section, no number) could pass as 0 because `fac.budget_of` falls back to a default. Here it must count as over.
- lesson-5: a parent split a second time (after a replan) could keep the first split's coverage if the save does not overwrite, and the join judge would then read stale points.
- lesson-9: tests that only check a clearly bad split would still pass with an off-by-one limit or a check that only matches names loosely. Test the 250/251 boundary and a near-miss name.

## Acceptance tests
- `tests/test_factory_knowledge.py::test_a_split_sub_gap_over_250_lines_is_sent_back`: a sub-gap of 251 net lines, and one with no number in its budget, are each sent back with the sub-gap named. The same split with 250 is accepted.
- `tests/test_factory_knowledge.py::test_a_single_plan_over_250_lines_is_still_accepted`: one definition of 400 net lines becomes the definition.
- `tests/test_factory_knowledge.py::test_a_split_without_one_coverage_block_is_sent_back`: no block, and two blocks, are each sent back. No sub-gap is requested and no plan file is written.
- `tests/test_factory_knowledge.py::test_a_coverage_point_naming_no_or_an_unknown_sub_gap_is_sent_back`: three cases are each sent back with the finding naming the point or name: a point with no `(by: …)`, one with `(by: )`, and one naming `alpha-on` when the sub-gap is `alpha-one`.
- `tests/test_factory_knowledge.py::test_a_sub_gap_no_coverage_point_names_is_sent_back`: in a three-sub-gap split whose points name only two of them, the third is named in the finding.
- `tests/test_factory_knowledge.py::test_accepted_coverage_is_the_parents_plan_and_a_resplit_replaces_it`: after an accepted split, `run/plans/<parent>.md` holds its points. A second accepted split of the replanned parent leaves only the new points. The lint sweep leaves the parent in `split`.
- `tests/test_factory_knowledge.py::test_a_sub_gaps_plan_review_is_given_the_parents_coverage`: the plan reviewer's saved brief for a sub-gap contains the parent's coverage points. For a gap with no parent it shows `(none)`.

## Size budget
70 net lines
size: M (confidence: medium)
