# run-budget-reserve: permissive P3, a day's AI budget that every block run of a YAML model reserves from before it starts
depends-on: []

## Definition of done

1. **Config.** A new top-level key `budget:` in `ergostat.yaml` takes two keys, and both are required. `daily` is US dollars over the trailing 24 hours, the same window as `ergostat.cost.usd`, with 0 < daily ≤ 10000. `max-cost` is dollars a run may reserve, with 0 < max-cost ≤ daily. Each of these is a compile error with its own message: an unknown key, a missing key, a non-number, or a value out of bounds. `ergostat.local.yaml` may not set `budget:` (it is not in `PER_MACHINE`). Without `budget:`, nothing in this gap changes how anything runs. The schema (`schema/ergostat.schema.json`) and SPEC describe the key.
2. **Which runs are charged.** The test is an allowlist. A block run is *free* (reserve 0) only when the block's type is not `ai` and its agent is declared with kind `person`, `decision`, `program` or `rule`. Every other run is *charged* and reserves `max-cost`, including blocks with no agent or no kind.
3. **The permissive.** `ergostat/costs/budget.py` has `permit(p, spec, block, ...)`. It opens `<state dir>/budget.lock` and holds `fcntl.flock(LOCK_EX)` across three steps: the read of the record, the decision, and the write of the reserving event. A new open of the file is made per call, so threads of one process and separate processes (the daemon and the `ergostat block --now` CLI) all exclude each other. The flock is the innermost lock taken: the dispatcher's `self.lock` may be held outside it, and nothing is acquired inside it except the event store's own append lock.
   - The decision refuses when `spent + reserved + reserve > daily`. It also refuses, failing closed, when the record cannot be read, or when the budget's values are out of bounds at run time: the same checks as at compile time, re-applied to the in-memory spec.
   - **Leased runs** (`Dispatcher.take`, used by the dispatch loop and by `dispatch.once`, i.e. `block --now` on a block that takes items) write `lease.taken` inside the permit. It carries `reserve` and `pid`.
   - **Unleased runs** (`Engine.run_block` with no item: the engine's loop, event triggers, `block --now`, the message classifier, step tests, library trials) write `agent.started` inside the permit, carrying `reserve` and `pid`.
   - A leased `run_block` does not reserve again. Its run id is the lease's `run`.
   - **When the permit refuses,** no `lease.taken` or `agent.started` is written, no lease is held, and the run is not left marked as running. A `budget.refused` event (item: the block; data: reserve, spent, reserved, daily, why) is written at most once a minute per block per process.
   - `ergostat block NAME --now` prints `refused: budget: …` and exits 1, for both a leased and an unleased block. It never reports an earlier run's result as this one.
4. **Spending is counted fail-closed.** The fold is keyed by run id (`lease.taken.data.run`, `agent.started.id`), never by lease state. Its inputs are reserving events from the last 7 days and ends from the last 24 hours. A run's charge is:
   - **No end yet:** its reserve, counted however old the reservation is within the 7-day lookback. A lease that expires, is released or nacked without an end changes nothing.
   - **Ended with known `cost_usd`:** that cost.
   - **Ended with unknown cost:** its reserve, or `max-cost` if it reported AI usage with no price.
   - **More than one end:** the largest charge.

   Ends are `agent.ran`, `agent.failed` and the new `budget.closed` (data: run, cost_usd or null, why). Free runs' ends in the window count their reported cost, and `max-cost` when they used AI at an unknown price. A run is matched to its end by `causedby`/`run`, never by time.
5. **Orphans are closed.** `budget.recover(p)` runs at engine start and on the dispatcher's watchdog pass, at most every 60 seconds. Under the flock, it writes `budget.closed` with `cost_usd: null` (charged at reserve for 24 hours from the close) for each reserving run with no end whose recorded `pid` is not alive, or whose `pid` is this process but which is not among the runs this process has open. Other cases:
   - A run that `run_block` raises out of after its `agent.started` gets a `budget.closed` with null cost from `run_block` itself.
   - A `lease.taken` that the item fold refused (another holder won) gets a `budget.closed` with `cost_usd: 0`, because nothing ran.
   - Stated limits, in SPEC: a reused pid keeps a reserve held until that process exits, and a run in flight for more than 7 days drops out of reserved.
6. **Measure.** `ergostat.budget.left` = daily − spent − reserved. It raises `MeasureError` when no `budget:` is declared or when the record cannot be read. It never returns `daily` or 0 in those cases, so `all_of` shows None and an `_error`.
7. **Scope, stated narrowly in SPEC and GAPS.** P3 governs every run started through `Engine.run_block` and `Dispatcher.take`. It does not cover:
   - ergostat's own judge passes (`Engine.judge`);
   - the AI calls inside ergostat that keep their own per-call caps (decisions extract, intent verdicts, the redesigner);
   - models in `ergostat.toml` (`runner.run_agent`), which have no `budget:`.

   GAPS.md gets an entry for bringing the in-ergostat AI calls under the budget, and another for T1 (`run-budget-trip`).
8. The house rules are met: the acceptance tests pass; the unit suite and the four browser files pass with rc 0; ruff is clean; origin/main is merged in and the suites are run again.

## Files to touch

- `docs/roadmap/overnight/run-budget-reserve.md` (the definition, first commit)
- `ergostat/costs/budget.py` (new: the fold, `permit`, `refused`, `recover`, `left`)
- `ergostat/spec/ir.py` (`RunBudget`, `Spec.budget`, the `ergostat.budget.left` measure name)
- `ergostat/spec/load.py` (`budget` added to `TOP`)
- `ergostat/spec/compile.py` (parse and bound `budget:`)
- `ergostat/spec/engine.py` (`run_block`: permit around `agent.started`, the crash close, `outcome["refused"]`; recovery at start)
- `ergostat/leases/dispatch.py` (`take`: permit around `lease.taken`, the lost-take close, a refused take; `once`: report refusal; watchdog: recovery)
- `ergostat/cli/spec_cmds.py` (`block --now`: print the refusal and exit 1)
- `ergostat/numbers/measures.py` (read `ergostat.budget.left`)
- `schema/ergostat.schema.json`
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_run_budget.py` (new)

## Risks

- **lesson-1.** The read of spent/reserved and the reserving write are at two call sites (`dispatch.take` and `run_block`) and in two processes (the daemon and the CLI). A lock held only around the read, or only in-process, lets two runs past a budget that has room for one. The flock must span the read, the decision and the write at both sites.
- **lesson-2.** Matching ends to starts by time, or deciding "newer" by `at`, could drop or double a charge. Match by run id. Use time only for the window.
- **lesson-3.** Several inputs can be missing or ambiguous: an expired or released lease, an unknown cost, an unreadable record, an orphaned `agent.started`, a lost take, an unpriced free run. Each must count as the reserve or refuse, never 0. `budget.left` must not report a value it could not compute.
- **lesson-4.** `daily` and `max-cost` move money. They need ceilings at compile time and again at permit time.
- **lesson-5.** Run ids are fresh (uuid4), but a retaken item gets a new run. The old lease's reserve must stay with the old run id and must not be merged into or cleared by the new one.
- **lesson-6.** A refused permit must leave no lease, no `running` mark, and no `agent.started` that holds a reserve with nothing behind it.
- **lesson-7.** New top key and new event types: `budget` must be classified in `load.py` (not settable locally), and `budget.*` events must not trip coherence or graph code. Merge main and run again.
- **lesson-8.** "No AI run starts" is narrowed to the start paths listed in point 7. A structural test fails if a new path that writes `agent.started` or `lease.taken` appears.
- **lesson-9.** Each test below names the code it guards. The report must say each was seen to fail with that code broken.
- **lesson-10.** The concurrency tests wait on events, not sleeps, when the code is broken. Their only timed wait is the bounded one that is expected when the lock works.
- **lesson-12.** Every point from the plan review is mapped to a test below.
- **lesson-13.** Failures outside these files are reported, not fixed.

## Acceptance tests

All in `tests/test_run_budget.py`.

**Config and limits**

- `test_check_budget_keys`: compile errors, each its own, for daily > 10000, daily = 0, daily < 0, max-cost = 0, max-cost < 0, max-cost > daily, missing max-cost, missing daily, an unknown key and a non-number. A valid `budget:` compiles. `budget:` in `ergostat.local.yaml` is refused. (lesson-4)
- `test_permit_refuses_out_of_bounds_at_run_time`: `spec.budget` is mutated after compiling to daily=20000, then max_cost=0, then max_cost>daily. Each time `run_block` writes no `agent.started`, and `budget.refused` says "out of bounds". Fails if the check exists only at compile time. (lesson-4)
- `test_no_budget_changes_nothing`: without `budget:`, the existing run and lease events carry no `reserve`, and runs start as before.

**Concurrency**

- `test_permit_lock_spans_write_run_block_then_take`: daily = 1.5 × max-cost. The hook `budget._between`, called after the read and before the write, is monkeypatched. In the first caller (`run_block`, unleased) it starts a competing `Dispatcher.take` in a thread and waits up to 1 s for the competitor's own `_between` to fire. The test asserts exactly one reserving event and one `budget.refused`. With the flock removed or moved off the write, the competitor reads during the gap, both write, and the test fails. (lesson-1)
- `test_permit_lock_spans_write_take_then_run_block`: the same with the roles swapped. (lesson-1)
- `test_permit_lock_across_processes`: the competitor is a subprocess calling `budget.permit` on the same state dir. It signals by writing a file after its read. Same assertions. Fails with a threading-only lock. (lesson-1)

**Refusal on every start path** (each fails if that path skips the permit)

- `test_refused_engine_loop`: through `Engine.start`.
- `test_refused_dispatch_loop`: an item ready under an exhausted budget stays unleased, and its state is unchanged.
- `test_refused_block_now_unleased`: through the CLI. Prints `refused: budget`, rc 1, and no `agent.started`. An earlier run's result is not reported.
- `test_refused_block_now_leased`: `block --now` on a block that takes items (`dispatch.once`). Same assertions.
- `test_only_known_start_paths`: an AST scan of `ergostat/`. The only places that add `agent.started` are `Engine.run_block`, `Engine.judge` and `runner.run_agent`, and the only place that adds `lease.taken` is `Dispatcher.take`. (lesson-8)
- `test_free_run_not_reserved`: a block with a `program` agent and a non-`ai` type runs under an exhausted budget and reserves 0. A block with no agent is charged. (Guards the allowlist; fails if the test is turned into a denylist.)
- `test_refusal_recorded_once_a_minute`: repeated refusals within 60 s give one `budget.refused` per block. (lesson-6, no flood)

**Fail-closed accounting**

- `test_reserve_held_until_end_with_cost`: a leased run's `lease.taken` with reserve, then `lease.expired` and `lease.ended` with no `agent.ran`. Still charged the reserve. After an `agent.ran` with cost 0.1 it is charged 0.1. Fails if reserved is read from held leases. (lesson-3)
- `test_end_without_cost_charges_reserve`: an end with no cost, or with unpriced AI, is charged the reserve (or `max-cost` for an unpriced free run). (lesson-3)
- `test_unended_reserve_does_not_age_out`: a reserve stamped 2 days ago, with a live pid and in this process's open runs, is still counted. An ended run older than 24 h is not counted. (lesson-3, lesson-2)
- `test_orphan_closed_by_recovery`: `agent.started` with the reserve and the pid of a reaped child process gets `budget.closed` with null cost. It is charged the reserve, and drops out 24 h after the close. A run with a live pid that this process has open is not closed. A run with this process's pid but not open here is closed.
- `test_run_block_crash_closes_reserve`: `Engine.program` is monkeypatched to raise after `agent.started`. Asserts a `budget.closed` and that the charge equals the reserve.
- `test_lost_take_releases_reserve`: the item fold refuses the take. Asserts a `budget.closed` with cost 0 and nothing reserved.
- `test_retaken_item_keeps_old_reserve`: an item taken, expired with no end, and taken again gives two run ids, each charged once. (lesson-5)

**The measure**

- `test_budget_left_value`: daily − spent − reserved, over a mix of runs.
- `test_budget_left_fails_closed`: with no `budget:`, `MeasureError`. With `events.query` monkeypatched to raise, it raises (not daily), and `all_of` gives None plus `_error`. A permit under the same fault refuses. (lesson-3)

## Size budget

380 net lines of code outside `tests/` and `docs/` (the schema JSON included).

## Notes from the plan review (answer each)

- Point 4's spending count reads run starts from the last 7 days but run ends from only the last 24 h, so a run that ended more than 24 h ago (but started within 7 days) looks unended. It is charged its full reserve for up to 7 days, and recover() writes a fresh budget.closed for it each day as the last one leaves the window, charging the reserve again each time. This also contradicts test_unended_reserve_does_not_age_out. Fix: read ends over the full 7 days so each start is matched to its end by run id, count an end's cost only if the end is within the last 24 h, and add a test: a run started 3 days ago and ended 2 days ago is charged 0 and recover writes nothing for it.
- Add a run to this process's open-runs list inside permit, under the file lock, so recover cannot close a run between its agent.started being written and its being listed; test it.
- recover must read the open-runs list without taking Dispatcher.self.lock inside the file lock, which would reverse the lock order point 3 sets; say so and test it.
- Say that a leased run_block's agent.started (same run id as the lease) carries no reserve and is not counted twice; assert it.
- lesson-6: the refused unleased-run test should also assert the block is not left marked as running.
- lesson-7: add a test (or name an existing one) showing budget.refused and budget.closed do not trip the coherence or graph code.
- lesson-8: SPEC and AGENT-GUIDE must not call max-cost a per-run spending cap; it is only the amount reserved before a run starts.
- Say how a run whose start is older than 7 days but whose end is within 24 h is charged: a priced run should be charged its real cost, not 0.
