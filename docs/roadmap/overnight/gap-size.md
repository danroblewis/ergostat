# gap-size: every planned gap carries a size class (S/M/L/XL) with a confidence, and the factory measures how often the class matched the lines it merged

depends-on: []

## Definition of done

- **Size line.** The planner's definition holds a line `size: S|M|L|XL (confidence: low|medium|high)` in its `## Size budget` section. The classes count net lines outside `tests/` and `docs/`, and `dev/` code counts: S is 50 or fewer (a net removal counts as S), M is 51 to 150, L is 151 to 400 and XL is over 400. `dev/prompts/planner.md` states these bounds and asks for low confidence when the planner is unsure. `fac.STANDIN["planner"]` carries a size line too.
- **Bad size lines are sent back.** `plan.py` reads the line from every definition (the gap's own, or each sub-gap's) and records `size` and `size_confidence` on that gap's `gap.planned`. A definition whose size line is missing, has an unknown class or has an unknown confidence counts as a planner problem: it is sent back like the other `problems()`, never defaulted to a class.
- **A replan replaces the size.** A replanned gap's new `gap.planned` replaces `size` and `size_confidence`, so no old class survives under the reused id.
- **Merged lines are recorded at merge.** The queue counts the merge's net lines from `pre` to the merged head, outside `tests/` and `docs/` with `dev/` included, and records them as `merged_lines` on `gap.merged`. If that count cannot be read, the merge still stands: `merged_lines` is left out and `merged_lines_error` says why. A gap merged again records the newer count.
- **The measures.** `measure.py size-accuracy` gives, over the 14-day window, the share of merged gaps with a `size` and a `merged_lines` whose lines fall inside their class. `measure.py size-accuracy-high` gives the same for high-confidence gaps only. A merged gap with a size but no `merged_lines` is never counted as a hit. It is left out of the share and listed on stderr. When nothing in the window can be measured, both exit 1 with "no value yet", never 0.
- **The model shows them.** Both measures are auxiliaries in `dev/model/measures.yaml` with sensors, so they appear on the diagram and in the Items tab. No new page or panel is added.
- **What is not covered is said.** Gaps whose definitions the coordinator wrote, and split parents (which merge nothing themselves), get no size and are outside the measure. `dev/README.md` describes the classes and the two measures and says this plainly.

## Files to touch

`dev/bin/plan.py`, `dev/bin/fac.py`, `dev/bin/queue.py`, `dev/bin/measure.py`, `dev/prompts/planner.md`, `dev/model/measures.yaml`, `dev/README.md`, `tests/test_factory_knowledge.py`, `tests/test_factory.py`

## Risks

- **lesson-3:** a missing size line could default to a class, or a merge with no line count could count as a hit or as 0 lines. Either would flatter the measure.
- **lesson-5:** a replanned gap, or a gap continued and merged again, could keep its old `size` or `merged_lines` under the same id.
- **lesson-8:** "accuracy measured" could be claimed for a measure that counts unmeasured gaps, or reports 0 when nothing can be measured.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_planned_gap_records_size_and_confidence`: a plan with `size: M (confidence: low)` records `size == "M"` and `size_confidence == "low"`. In a split, each sub-gap records its own class.
- `tests/test_factory_knowledge.py::test_plan_without_valid_size_is_sent_back`: a missing size line, a class `XXL`, or a confidence `sure` each give `gap.plan-sent-back` with a finding naming the size, and nothing is planned (lesson-3).
- `tests/test_factory_knowledge.py::test_replan_replaces_size`: a gap planned as S, sent back, then replanned as L reads L with the new confidence (lesson-5).
- `tests/test_factory.py::test_merge_records_merged_lines`: a branch adding 30 lines in `dev/bin/`, 20 in `ergostat/` and 100 in `tests/` merges with `merged_lines == 50`. A second merge of the same gap records its new count (lesson-5).
- `tests/test_factory.py::test_merge_stands_when_lines_unreadable`: when the line count raises (monkeypatched), `gap.merged` is still said, with no `merged_lines` and with a `merged_lines_error` (lesson-3).
- `tests/test_factory_knowledge.py::test_size_accuracy_counts_hits_over_measured`: four merged gaps in the window are recorded: S with 40 lines (a hit), M with 300 (a miss), XL with 900 (a hit) and L with no `merged_lines`. The measure reads 0.667, so the unmeasured gap is not a hit. A gap merged outside the window does not change it (lesson-8).
- `tests/test_factory_knowledge.py::test_size_accuracy_high_only_and_no_value`: `size-accuracy-high` counts only the high-confidence gaps. With no measurable gap, both measures exit 1 (lesson-3, lesson-8).

For each test, the implementor reports breaking the code it guards and watching it fail (lesson-9).

## Size budget

`size: M (confidence: medium)`

110 net lines (all in `dev/`. `fac.net_lines` counts 0 core lines for this branch).

## Notes from the plan review (answer each)

- Merged lines at merge: 'merged_lines is left out' on an unreadable count is wrong under a fold that merges fields. A gap merged again whose count fails keeps the earlier merge's merged_lines under the same id and is scored on stale lines (lesson-5 with lesson-3). The definition must say the newer gap.merged clears any earlier merged_lines (for example, written as null, or the fold resets both fields on every gap.merged), and the measure must treat a gap whose latest merge has merged_lines_error as unmeasured. Add an acceptance test: merge with a count, merge again with the count monkeypatched to raise; merged_lines is absent or null, the error is present, and size-accuracy leaves the gap out of the share and lists it on stderr. The current test_merge_stands_when_lines_unreadable only covers a first merge, so it cannot fail on this.
- Test the class bounds at the edges: 50->S, 51->M, 150->M, 151->L, 400->L, 401->XL, and a negative count->S. An off-by-one in the classifier passes the current 40/300/900 test.
- size-accuracy-high: say and test that it exits 1 with 'no value yet' when low-confidence gaps can be measured but no high-confidence gap can, not only when nothing can be measured.
- State which timestamp the 14-day window uses (the latest gap.merged of the gap) and test a gap first merged outside the window and merged again inside it.
- Assert that the unmeasured gap is listed on stderr in test_size_accuracy_counts_hits_over_measured; the definition promises it and no test checks it.
- Say whether a replan after a merge (a gap continued) clears merged_lines, so a new size is never scored against the old branch's lines before it merges again.

## Where it stopped

Built, round 1. Every item of the definition of done is in, with the deviations and answers below. Nobody could be
asked, so where the definition and the plan review's notes differ, the review's (stricter) reading was taken.

**Deviation from "merged_lines is left out".** Every `gap.merged` writes both fields: `merged_lines` (the count) with
`merged_lines_error: null`, or `merged_lines: null` with `merged_lines_error`. Under the record's replace fold, leaving
the field out would keep an earlier merge's count under the same id. A null `merged_lines` is "left out" of the
measure, never 0.

**The plan review's notes, answered:**
- Re-merge with a failing count: the newer `gap.merged` writes `merged_lines: null` and the error. The measure counts a
  gap only when `merged_lines` is an integer and there is no `merged_lines_error`. Test:
  `tests/test_factory.py::test_a_merge_again_whose_count_fails_keeps_no_old_count` (merge with 40 lines, merge again
  with the count raising: null, error present, `size-accuracy` exits 1 and names the gap on stderr).
- Class edges: 50->S, 51->M, 150->M, 151->L, 400->L, 401->XL, -30->S, 0->S are asserted in
  `test_size_accuracy_counts_hits_over_measured`.
- `size-accuracy-high` with only low-confidence gaps measurable (and a high one unmeasured) exits 1 with "no value yet":
  `test_size_accuracy_high_only_and_no_value`.
- The window is on the gap's latest merge (`merged_at`, replaced by each `gap.merged`). A gap first merged 20 days ago
  and merged again yesterday is counted, which the test asserts (0.667 -> 0.5).
- The unmeasured gap is asserted on stderr in `test_size_accuracy_counts_hits_over_measured`.
- A replan clears `merged_lines` and `merged_lines_error` (`gap.planned` writes both as null), so a new size is never
  scored against an earlier branch's lines. Asserted in `test_replan_replaces_size`. A split also clears a parent's
  earlier `size` and `size_confidence` (`gap.split`), so a gap first planned whole and then split is not measured.

**Beyond the listed tests.** In a split, one sub-gap's bad size line sends the whole plan back and no sub-gap is made.
A size line outside `## Size budget` is not taken.

**Known limit (said in dev/README.md).** The backlog groomer (`backlog.py`, `gap.groomed`) also writes a field named
`size` (S/M/L or hours), including on gaps already planned. The measure counts only gaps with a planner's
`size_confidence`, so a coordinator-written gap the groomer sized is never measured. But a groomer regrade after the
plan replaces the planner's class, and that regrade is then what is scored. A fix belongs in `backlog.py`: do not
write `size` on a gap that has `size_confidence`. That file is outside this gap's list, so it is left for its own gap.

**Lesson-9, each test broken and watched fail:**
- Not recording the size on `gap.planned` failed `test_planned_gap_records_size_and_confidence` and
  `test_replan_replaces_size`.
- Leaving size findings out of `problems()` failed all three cases of `test_plan_without_valid_size_is_sent_back`.
- Not clearing `merged_lines` on `gap.planned` failed `test_replan_replaces_size`.
- Counting core lines only (dev/ excluded) failed `test_merge_records_merged_lines` (20 != 50).
- Omitting `merged_lines` on a failed count failed `test_merge_stands_when_lines_unreadable` and
  `test_a_merge_again_whose_count_fails_keeps_no_old_count` (40 survived).
- Testing S with `< 50` failed the edge assertions.
- Scoring unmeasured gaps as misses failed both measure tests and the re-merge test.
- Dropping the high-only filter failed `test_size_accuracy_high_only_and_no_value`.
- Ignoring the window failed `test_size_accuracy_counts_hits_over_measured`.

**Size.** About 74 net lines in `dev/` (45 in `dev/bin`, plus the model, the prompt and README), and 0 core lines.
That is within the 110 budget and is class M.

**Not run here.** The whole unit suite and the browser files (the factory runs them under the watchdog). There is no
remote in this container, so origin/main could not be fetched. Local `main` has not moved past the branch base.
