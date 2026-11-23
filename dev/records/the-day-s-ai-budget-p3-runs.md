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

## Where it stopped

Round 1: built, awaiting review. No code changed; `docs/GAPS.md` (the P3 entry only) and this section are the diff.

Choice made alone (the more reversible one): this definition may change only by appending this section, so the
evidence that done point 1 asks the record to hold is written here rather than edited into the text above.

Merge commit: c8c94527 (`Merge branch 'factory/run-budget-reserve'`). Evidence on main, for each point of
`docs/roadmap/overnight/run-budget-reserve.md` (tests are in `tests/test_run_budget.py`):

1. Config: `ergostat/spec/load.py` (`budget` in `TOP`, not in `PER_MACHINE`), `ergostat/spec/compile.py`
   (`budget`), `schema/ergostat.schema.json` (`budget`). Tests: `test_check_budget_keys`,
   `test_empty_budget_is_two_errors`, `test_no_budget_changes_nothing`.
2. Charged runs, an allowlist: `ergostat/costs/budget.py` (`FREE`, `reserve_of`). Tests: `test_free_run_not_reserved`,
   `test_free_run_allowlist`.
3. The permit: `ergostat/costs/budget.py` (`permit` under `fcntl.flock`, `refused`), `ergostat/spec/engine.py`
   (`run_block`), `ergostat/leases/dispatch.py` (`take`, `once`), `ergostat/cli/spec_cmds.py` (`refused: budget:`).
   Tests: `test_permit_lock_spans_write_run_block_then_take`, `test_permit_lock_spans_write_take_then_run_block`,
   `test_permit_lock_across_processes`, `test_permit_refuses_out_of_bounds_at_run_time`, `test_refused_engine_loop`,
   `test_refused_dispatch_loop`, `test_refused_block_now_unleased`, `test_refused_block_now_leased`,
   `test_refusal_recorded_once_a_minute`, `test_leased_run_block_reserves_once`.
4. Spending counted fail-closed, by run id: `ergostat/costs/budget.py` (`fold`). Tests:
   `test_reserve_held_until_end_with_cost`, `test_end_without_cost_charges_reserve`,
   `test_malformed_cost_counts_unknown`, `test_unended_reserve_does_not_age_out`, `test_window_by_run_id`,
   `test_retaken_item_keeps_old_reserve`.
5. Orphans closed: `ergostat/costs/budget.py` (`recover`, `close`), called from `ergostat/spec/engine.py` at start and
   from `ergostat/leases/dispatch.py` on the watchdog pass. Tests: `test_orphan_closed_by_recovery`,
   `test_permit_lists_the_run_under_the_lock`, `test_recover_copies_open_before_reading`,
   `test_run_block_crash_closes_reserve`, `test_lost_take_releases_reserve`,
   `test_take_raced_by_the_stop_releases_reserve`, `test_taken_then_stopped_before_its_run_releases_reserve`,
   `test_recovery_failure_skips_no_watch`.
6. The measure: `ergostat/numbers/measures.py` (`ergostat.budget.left`, read through `budget.left`). Tests:
   `test_budget_left_value`, `test_budget_left_fails_closed`.
7. Scope, stated narrowly: SPEC §9.9 and the P3 entry in `docs/GAPS.md`. Test: `test_only_known_start_paths`. The
   `budget.*` events are ergostat's own and trip nothing: `test_budget_events_written_only_by_ergostat`,
   `test_budget_events_trip_no_coherence_or_graph`.
8. House rules: on this branch `tests/test_run_budget.py` gives 39 passed (35 test functions, some parametrized; the
   "34 tests" above is the count at the merge), so none fails on main, and ruff is clean. The unit suite and the four
   browser files were not run by the implementor: by the factory's rule they run in its build step and the merge
   queue.

No other gap is needed first. Merge main again before landing and read the P3 entry again afterwards (lesson-7).

## Entry

section: Runtime, scale and latency

- **The day's AI budget, P3: runs reserve before they start** (in progress, `factory/run-budget-reserve`; SPEC §9.9,
  `docs/roadmap/overnight/run-budget-reserve.md`): `budget: {daily, max-cost}`; every run started through
  `Engine.run_block` or `Dispatcher.take` (and, with `[budget]` in `ergostat.toml`, `runner.run_agent`) asks a permit under a file lock, and a charged run is refused unless what
  is left of the day covers `max-cost`; spend is folded by run id, an unknown cost charged as the reserve;
  `ergostat.budget.left`. It covers those start paths only.
