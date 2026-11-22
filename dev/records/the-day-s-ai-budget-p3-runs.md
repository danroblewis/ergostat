# the-day-s-ai-budget-p3-runs: P3 is already on main; mark its GAPS entry done and record the evidence
depends-on: []

## Definition of done

P3 was built on `factory/run-budget-reserve` and merged into main in c8c94527. Main already has all of it:
- `budget: {daily, max-cost}` checked at compile time (`ergostat/spec/load.py`, the schema);
- `costs/budget.py` with `permit` under `flock`, `fold` keyed by run id, `recover` and `left`;
- the permit on `Engine.run_block` and on `Dispatcher.take`;
- `ergostat.budget.left` in `ergostat/numbers/measures.py`, and SPEC §9.9;
- 34 tests in `tests/test_run_budget.py`.

This branch adds no code. When it is done:
1. `dev/records/the-day-s-ai-budget-p3-runs.md` (new) is this definition. It names the merge commit, and for each point
   of `docs/roadmap/overnight/run-budget-reserve.md` it names the main file and the test in
   `tests/test_run_budget.py` that shows that point.
2. The P3 entry in `docs/GAPS.md` reads `done`, not `in progress`, and points to SPEC §9.9 and the record. Its scope
   sentence stays narrow: P3 itself covers only the `Engine.run_block` and `Dispatcher.take` start paths. ergostat's own
   AI calls are covered by `ai-calls-ask-the-budget`. `ergostat.toml` models are still left to `toml-models-budget`,
   which is not merged. No other GAPS entry changes, and the text is not spliced into a neighbouring entry.
3. The acceptance tests below pass on the branch unchanged. The unit suite and the four browser files pass with rc 0,
   and ruff is clean. origin/main is merged in and the suites are run again.
4. If any test in `tests/test_run_budget.py` fails on main, the report says so and names it. It is not fixed here.

## Relation to other work

- `merge-pipeline-gaps-md-regenerated-on-land`: it is writing `docs/GAPS.md` from the records. This branch edits only
  the one P3 entry, so it is a small conflict risk. Merge main again before landing.
- `toml-models-budget`: not merged. Its "Left" clause in the ai-calls entry stays as it is.
- `run-budget-ledger`, `run-budget-trip`, `ai-calls-ask-the-budget`: merged. They build on P3, and nothing here touches them.

## Files to touch

- `dev/records/the-day-s-ai-budget-p3-runs.md` (new)
- `docs/GAPS.md`

## Risks

- lesson-7: a merge of main can splice the P3 entry into a neighbouring entry. Check the entry's text again after
  every merge.
- lesson-8: the done entry must not claim more than P3 covers. `ergostat.toml` runs and the judge's own scope are
  stated as they are on main.
- lesson-13: a failure outside these files is reported, not fixed here.

## Acceptance tests

- `tests/test_run_budget.py::test_permit_lock_across_processes`: the read, the decision and the write are held under
  one file lock, across processes.
- `tests/test_run_budget.py::test_refused_block_now_leased`: a refused leased `block --now` prints the refusal and
  exits 1.
- `tests/test_run_budget.py::test_refused_engine_loop`: a refused run in the engine loop writes no `agent.started`
  and leaves no `running` mark.
- `tests/test_run_budget.py::test_only_known_start_paths`: no unlisted start path exists.
- `tests/test_run_budget.py::test_budget_left_fails_closed`: the measure gives no value when the record cannot be read.
- `tests/test_run_budget.py::test_retaken_item_keeps_old_reserve`: each run id is charged once.

## Size budget

0 net lines of code outside `tests/` and `docs/`. The record in `dev/` is prose, and nothing else changes.
size: S (confidence: high)
