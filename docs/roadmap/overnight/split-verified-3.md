# split-verified-3: split quality measured: `split-quality`, `split-joins` and `split-overhead` from the join judge's verdicts and the children's costs
depends-on: [split-verified-2]

## Definition of done
- **`split-quality`.** `measure.py split-quality` gives a share. It counts the split parents whose first join verdict falls in the 14-day window, and reports the share of them whose first verdict was `covered`. "First" means the first entry of the parent's `join_verdicts` list, which is in record order. It is never chosen by comparing `at` times. A parent that was judged `short` and later `covered` counts as not covered. When no parent was judged in the window there is no value (exit 1), never 0.
- **`split-joins`.** `measure.py split-joins` counts every split parent that has at least one join verdict, over the whole record with no window. This is the "5 joins" that gap/plan-by-size's XL rule waits for.
- **`split-overhead`.** This is the median, over split parents merged in the window, of a ratio for each parent. The ratio's top is the parent's own `ai_cost_usd` plus the `ai_cost_usd` of each of its `children`, including join sub-gaps. Its bottom is the median `ai_cost_usd` of merged unsplit gaps (no `parent`, no `children`, a counted `merged_lines`), over the whole record, in the size class of the children's summed `merged_lines`. The classes are those of `size_class`.
  - A parent is left out, and named on stderr, when a child is not merged, a child has no `merged_lines` or has `merged_lines_error`, a child has no `ai_cost_usd`, or the class has no unsplit gap. A parent that is left out never counts as a ratio of 0 or 1.
  - When no parent is left in, there is no value (exit 1).
- **In the model.** `dev/model/knowledge.yaml` declares the three as auxiliaries of system `intake` next to `splits-clean`, each with a `measure.py` sensor and a description that matches the code. `ergostat check` on the factory's model shows no new error or finding.
- **Written down.** The docstring of `measure.py` lists the three, and the measures that have no value with nothing to measure include `split-quality` and `split-overhead`. `dev/README.md`'s planner paragraph names them in one sentence and says that `split-quality ≥ 0.7` over at least 5 joins is the condition gap/plan-by-size gates XL auto-split on. This gap does not build that gate.

## Relation to other work
- gap/split-verified-2: builds on it. It reads the `join_verdicts` list and the parent's `children` that the join judge records.
- gap/plan-by-size: comes after this. Its XL rule reads `split-quality` and `split-joins`. Both touch `dev/bin/measure.py`, `dev/model/knowledge.yaml` and `dev/README.md`, so merge origin/main and run the suites again. `tests/test_factory_knowledge.py` (its file) is avoided.

## Files to touch
- `dev/bin/measure.py`
- `dev/model/knowledge.yaml`
- `dev/README.md`
- `tests/test_factory_join.py`

## Risks
- lesson-2: picking a parent's "first" verdict by the smallest `at` could pick wrongly when two verdicts share a time. The list order (the fold's append, in seq order) decides.
- lesson-3: a child with no `merged_lines`, a child with no cost, a child not merged, or a class with no unsplit baseline could count as 0 and shrink the overhead. Each such parent is left out and named, and with none left there is no value.
- lesson-8: a docstring or README line saying "every split" or "the parent's cost" while the code drops parents, or leaves out the parent's own planning and judge cost. Each claim must have a test below.

## Acceptance tests
- `tests/test_factory_join.py::test_split_quality_counts_each_parent_by_its_first_verdict`: three judged parents: `covered`; `short` then `covered`; `short`. The reading is 0.333. In the second parent the two verdicts carry the same `at`, and the result is still `short`-first. A parent judged only before the window is not counted.
- `tests/test_factory_join.py::test_split_quality_has_no_value_with_no_parent_judged`: there are split parents but none has a verdict in the window, so it exits 1 and prints nothing to stdout.
- `tests/test_factory_join.py::test_split_joins_counts_judged_parents_over_the_whole_record`: one parent judged 30 days ago, one judged twice today, and one parent with no verdict give 2.
- `tests/test_factory_join.py::test_split_overhead_is_the_split_cost_over_the_unsplit_median_of_its_class`: a parent costs 2, and two children cost 10 and 8 with 60 and 50 lines (110, class M). Unsplit M gaps cost 5, 10 and 40, and an unsplit S gap costs 1. The reading is 2.0.
- `tests/test_factory_join.py::test_split_overhead_leaves_out_a_parent_it_cannot_price`: one priced parent sits next to four that cannot be priced: a child with no `merged_lines`, a child with no `ai_cost_usd`, an unmerged child, and a class with no unsplit gap. The reading is that one parent's ratio, and stderr names each of the other four. With only the unpriceable ones present it exits 1.
- `tests/test_factory_join.py::test_the_split_measures_are_sensed_in_the_factory_model`: the compiled factory model has the three auxiliaries in `intake`, each with a sensor running `measure.py` with its own name. `measure.py`'s docstring names each of them.

## Size budget
70 net lines
size: M (confidence: medium)

## Where it stopped
Built: everything above, the six acceptance tests passing. Notes for the review:
- **Size.** 79 net lines in `dev/`: `measure.py` +56 (about 44 of code, the rest its docstring), `knowledge.yaml` +18,
  `dev/README.md` +5. That is 9 over the 70. The overrun is the written-down claims (the docstring and README), which
  lesson-8 asks to be exact about who is left out. The code alone is within budget.
- **Choices taken where the definition is silent (the most reversible ones).**
  - A split parent is a gap with a non-empty `children`.
  - `split-overhead` takes only parents whose state is `merged` and whose `merged_at` is in the window.
  - A parent with no usable `ai_cost_usd` of its own is also left out and named. "Usable" means missing, not a
    number, negative or NaN is refused. This is a fifth reason, added so the parent's cost never counts as 0
    (lesson-3).
  - An unsplit gap with no usable cost is left out of its class's baseline, never counted as 0.
- **Not run here.** `ergostat check` was refused as a shell command. The first join test covers it instead: it compares
  the model's problems against main's, and it passed. The clone has no `origin` remote and `git fetch` was refused, so
  origin/main was not merged. Local `main` has nothing the branch lacks. The unit suite and the four browser files were
  not run by me: that is left to the factory's suites.
- **Lesson-9.** I broke the guarded lines and the tests failed. Taking the last verdict failed the quality test. Dropping
  the window failed both quality tests. Dropping the parent's own cost failed both overhead tests. Letting an unmerged
  child through failed the leave-out test.

### Round 2
- **Main merged.** The factory's merge of main (e1e778c1) conflicted in `measure.py`'s docstring. Both sides were kept:
  main's manager measures line and the branch's three split measures.
- **The blocking finding (continued sub-gaps).** `split-overhead` now takes a parent's sub-gaps as its `children`,
  plus the gaps whose `parent` names it, plus each one's `resumed_as` chain (`family`). A sub-gap whose `parent` no
  longer names the parent is one `parks.split_again` unlinked: it is stopped and replaced. Its cost counts. Its lines
  do not count, and it need not be merged. Every other sub-gap must still be merged, sized and priced. The docstring,
  the model's description and the README say so. New test:
  `test_split_overhead_prices_a_parked_sub_gap_and_its_continuation`. Lesson-9: with children only, it fails (exit 1,
  "a child not merged"). Leaving out the stopped one's cost gives 1.8. Counting its lines gives class XL, which is left
  out.
- **The non-blocking finding (the import from `tests/test_factory_knowledge.py`).** Kept. That import came with
  gap/split-verified-2 and is on main as it is. This gap only avoids editing that file, as its definition says.
  Copying `Instance` here would duplicate a large fixture.
- **Size, round 2.** 92 net lines in `dev/` (`measure.py` +68, `knowledge.yaml` +18, `dev/README.md` +6), 22 over
  the 70. The fix adds 13: the `family` walk and the wording that names who is left out (lesson-8).
- **Run.** `tests/test_factory_join.py` (13 passed) and ruff (clean). Not run: the unit suite and the four browser
  files, which are left to the factory's suites. No origin remote here: main is the factory's merge above.
- **The failed unit run after round 2.** Its tail ends in one line of dots: no `FAILED` line, no test named, no
  summary. That reads as a run cut off (a time limit or the watchdog), not a failing test. I found nothing to fix. The
  merge of main was already committed (e9a94511), with no conflict left. I ran, one batch at a time, every file that
  reads what this branch changes (`measure.py`, the factory model, `knowledge.yaml`). `test_factory_join.py`: 13
  passed. `test_spec_compile`, `test_local_settings`, `test_factory_resources`, `test_backlog` and
  `test_factory_sessions`: 63 passed. `test_factory_knowledge` and `test_factory_manager`: 107 passed.
  `test_factory.py`: 126 passed, 2 skipped. Ruff on `ergostat tests scripts` is clean. Not run: the whole unit suite
  (left to the factory) and the four browser files. `test_factory_join.py` is slow (152 s alone, 7 of its 13 tests
  from this gap), and it is marked `slow`, so it starts first. If the unit run was cut off for time, this may be the
  cause. It is a cost of the acceptance tests the definition names, not a bug, so I left it as it is.
