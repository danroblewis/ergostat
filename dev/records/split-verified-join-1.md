# split-verified-join-1: the join judge's remaining edges (no `merged_at` on a covered parent, a missing sub-gap judged short without a session, the second short parks, a taken name not fatal) and the two split measures `splits-covered` and `split-budgets-held`
depends-on: [split-verified-3]

## Definition of done
- **Covered, but not a merge of work.** When `plan.py join` judges a parent covered, the parent moves to `merged` with its verdict, `join_verdicts` and `judged_at`, but with no `merged_at`. Because of this it stays out of cycle-hours, cost-per-merged and fix-rounds. `split-overhead` now finds split parents in the window by `judged_at` (their latest verdict), not by `merged_at`, and gives the same values as today on the existing tests once their fixtures are moved to `judged_at`.
- **Missing sub-gap, no session.** `join_brief` shows some inputs as `(missing: …)`. If any sub-gap's definition or last review is one of them (including a child that is not in the record), `plan.py join` makes no clone and no AI call. It records a `short` verdict with one point per missing sub-gap that names the sub-gap and what could not be read, with cost 0. From there it takes the normal short path (a new sub-gap is requested, or the gap is parked).
- **The second short parks.** The first `short` verdict requests a new sub-gap and splits again. The second parks the parent, and its "Where it stopped" text lists the points not built, one `- ` line each. The constant and the `join_judge` brief's `most_short` agree with this.
- **A taken name is not fatal.** If the sub-gap name the join would give (`<parent-branch>-join-<n>`) already exists as an id or a branch, the join takes the next unused safe name. It no longer raises and leaves the gap in `joined`.
- **`splits-covered`.** This is today's `split-quality` under the entry's name, with the same rule: of the parents whose first verdict (the first entry of `join_verdicts` in list order, never chosen by comparing `at` times) is in the 14-day window, the share whose first verdict was covered. With none to count there is no value (exit 1). The name `split-quality` is gone everywhere it appears: `measure.py`, `dev/model/knowledge.yaml`, `dev/README.md`, `docs/roadmap/overnight/knowledge.md` (including the plan-by-size condition sentence) and `docs/proposals/knowledge-graph.md`.
- **`split-budgets-held`.** Of the sub-gaps (gaps with a `parent`) merged in the window, this is the share whose recorded `net_lines` are at or under the net lines in their own definition's `## Size budget`. It reads the definition where `brief.definition_text` finds it. A missing or unreadable definition, a budget with no number, or a missing `net_lines` counts as not held. It never uses `budget_of`'s default of 600. With nothing to count there is no value (exit 1).
- Both measures are auxiliaries in `dev/model/knowledge.yaml` with a `measure.py` sensor, next to `split-joins`. `ergostat check` on the factory model shows no new finding.
- `dev/README.md` and `docs/roadmap/overnight/knowledge.md` describe "covered" as the planner's coverage mapping plus an AI judgment at the join, not a proof, and name `splits-covered` and `split-budgets-held`.

## Relation to other work
- gap/split-verified-3: builds on it (its `split-quality` is renamed; its `split-overhead` is windowed on `judged_at`).
- gap/code-health-measures: also edits `dev/bin/measure.py` and `dev/README.md`; this change keeps to the split functions and the split paragraph.
- gap/gaps-landed-stock: also edits `dev/model/knowledge.yaml`; this change adds only the two auxiliaries next to `split-joins`.

## Files to touch
- `dev/bin/plan.py`
- `dev/bin/measure.py`
- `dev/model/knowledge.yaml`
- `dev/README.md`
- `docs/roadmap/overnight/knowledge.md`
- `docs/proposals/knowledge-graph.md`
- `tests/test_factory_join.py`
- `tests/test_factory_knowledge.py`

## Risks
- lesson-3: a missing sub-gap definition or review could still reach the judge and come back covered. A missing budget could fall back to 600, or a missing `net_lines` could be read as 0, and count as held. Each of these must count as the worst case.
- lesson-2: "first verdict" picked by the earliest `at` instead of list order. The test gives the first entry a later `at` than the second.
- lesson-9: the cycle-hours check must include a merged parent, so that a `merged_at` left on it would change the value.

## Acceptance tests
- `tests/test_factory_join.py::test_join_moves_parent_to_joined_then_judge_merges`: a covered verdict leaves the parent `merged` with `judged_at` and its verdict but no `merged_at`. cycle-hours, cost-per-merged and fix-rounds read the same before and after the judgment.
- `tests/test_factory_join.py::test_join_with_missing_sub_gap_definition_is_not_covered`: the first run has one sub-gap with no readable definition, the second a sub-gap with no recorded review. `fac.attempt` is patched to fail if called. Each run records `short` with a point naming that sub-gap, at cost 0.
- `tests/test_factory_join.py::test_join_not_covered_requests_new_gap_then_second_parks`: the first short requests a sub-gap, here under a new id because the name the join would give is already recorded. The second short parks the parent, and the park text lists the points not built.
- `tests/test_factory_knowledge.py::test_split_measures`: covers `splits-covered` (a parent covered only on its second judgment is not counted as covered, even when its first entry has the later `at`; no value with nothing in the window) and `split-budgets-held` (at budget is held; one line over, a missing budget section and a missing `net_lines` are each not held; no value with no sub-gap merged in the window). Both are sensed in `knowledge.yaml` as auxiliaries.
- `tests/test_factory_join.py::test_split_overhead_is_the_split_cost_over_the_unsplit_median_of_its_class`: still passes with the parent given `judged_at` and no `merged_at`.

## Size budget
90 net lines
size: M (confidence: medium)
