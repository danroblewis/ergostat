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

## Where it stopped

Round 1: built, awaiting review. All the acceptance tests exist in `tests/test_run_budget.py` and pass, with four
more the plan review asked for (`test_permit_lists_the_run_under_the_lock`, `test_leased_run_block_reserves_once`,
`test_budget_events_trip_no_coherence_or_graph`, and the 3-days/2-days case inside
`test_unended_reserve_does_not_age_out`). Net lines outside `tests/` and `docs/`: 337 of the 380.

Choices made alone (each the more reversible one):

- The lease event's real type is `ergostat.lease.taken`; "lease.taken" in this file means that event.
- A free run still writes `reserve: 0` and its `pid` on its `agent.started`, so the fold can tell it from a run with no
  reserving event. It asks no decision, but an out-of-bounds budget refuses free runs too (failing closed).
- An end whose run has no reserving event in the 7 days (a free run, a start over 7 days old, `Engine.judge`,
  `runner.run_agent`) counts its known cost, `max-cost` when it used AI at no known price, and otherwise 0.
- An end counts only while it is within the last 24 h. When a run has several ends, the largest charge among those
  in the window counts.
- A take that wins its lease but whose run never starts (it raced ergostat's stop) is not closed at 0. It is dropped
  from the open runs, so recovery closes it at its reserve (point 4: a released lease changes nothing).
- Recovery also runs on the dispatcher's one-second clock (limited to once a minute), even when no block takes items,
  so a CLI's orphan is closed without waiting for the next engine start.
- `graph.py` was not changed. It shows `budget.*` on the `ergostat` agent's node the same way it shows the lease
  events. The test holds that the wiring, coherence and every part's node stay unchanged.

Answers to the plan review:

- Ends over 7 days, matched by run id, their charge counted only within 24 h: `fold` and `read` in
  `ergostat/costs/budget.py`. A run started 3 days ago and ended 2 days ago is charged 0, and recovery writes nothing
  for it (`test_unended_reserve_does_not_age_out`).
- A run is added to `OPEN` inside `permit`, under the flock, before its write
  (`test_permit_lists_the_run_under_the_lock`).
- `recover` reads `OPEN.copy()` and takes no lock but the flock and the store's own. It completes while another
  thread holds the dispatcher's and engine's locks (`test_orphan_closed_by_recovery`).
- A leased `run_block`'s `agent.started` has the lease's run id and no `reserve`. It is counted once
  (`test_leased_run_block_reserves_once`).
- The refused unleased run leaves the block off `running` and `last_run` (`test_refused_engine_loop`).
- lesson-7: `test_budget_events_trip_no_coherence_or_graph`.
- lesson-8: SPEC §9.9 and the agent guide §3b say `max-cost` is only what a run reserves, not a cap on its spending.
- A start older than 7 days with an end within 24 h: charged its real cost when priced, `max-cost` for AI at no known
  price, and otherwise 0, a limit stated in SPEC §9.9 (`test_unended_reserve_does_not_age_out`, the `ancient` run).

Each test was seen to fail with the code it guards broken by hand, then restored. Lock checks: no flock; a
threading-only lock, which fails only the cross-process test; the flock released before the write. Start paths: both
start paths skipping the permit; `once` and the CLI ignoring the refusal. Bounds: checked at compile time only.
Allowlist: turned into a denylist. Fold: ends read over 1 day; a lease's end treated as the run's end; unknown cost
as 0; the leased run reserving again. Recovery: sparing every run of this pid; closing open runs; `OPEN` not filled in
the permit. Closes: the crash close and the lost-take close removed. Fail-open: `left` and the permit on an
unreadable record. Rate: the once-a-minute limit removed.

Not done here: merging origin/main. This clone has no `origin/main` ref and no network, and local `main`
(1e9ecb16) is this branch's base, so there was nothing to merge. The full unit suite and the four browser files
were not run here either; the factory runs them, under the watchdog. Run here, one batch at a time: the new file and
17 existing test files that touch these modules (leases, schema, structure, costs, CLI fallback, run logs,
architecture, coherence, runner, streamed output, messages, control, resilience, claims, workspaces, auxiliaries,
gated actions).

After the factory's fast suites: its `unit` tail held only the package build, no pytest line and no line from
`suite_watch` (which prints its JSON line at any end it sees), so it names no failing test. Not reproduced here.
`-n 8` was not run here (the rules keep a parallel run of the whole suite for the factory). The whole unit suite was run
serially, twice: the first run stopped at its first failure, and the second deselected that test. Across the two,
7 failed, none in this gap's files. The second run: 2373 passed, 69 skipped, 6 failed. Each of the 7 passes when its file
is run alone:

- Five multiprocessing tests: `test_index_files.py` (four tests), `test_modelling_ai_cap.py::test_two_runs_cannot_both_take_the_last_of_the_cap`
  and `test_store_conformance.py::test_a_second_instance_threads_and_processes_lose_nothing[sqlite]`.
  Four show `ImportError: cannot import name 'Empty' from 'queue' (/work/dev/bin/queue.py)` in their spawned
  children. The store test lost exactly the 50 events its extra process should have written. The cause is
  `tests/test_backlog.py`, `tests/test_factory.py` and `tests/test_factory_times.py` inserting `dev/bin` into
  `sys.path`, so every later spawn child in the same process imports `dev/bin/queue.py` as `queue`. That is on
  main, it depends on test order, and it is outside this gap (lesson-13).
- `test_modeller.py::test_a_response_with_no_cost_is_charged_its_reservation[missing]`: the modeller's own AI cap,
  which this gap does not touch.

No code was changed for this round: no failure traced to this branch was found.

Round 2: main (e1e778c1) is merged in. It conflicted in `ergostat/numbers/measures.py` and `ergostat/spec/ir.py`,
where main's `ergostat.upkeep.*` measures sat next to this branch's `ergostat.budget.left`. Both were kept: the
`budget.` and `upkeep.` short prefixes, both lists of names in `measure` and `all_of`, and `RunBudget` beside
`UPKEEP`. Net lines outside `tests/` and `docs/`: 347 of the 380.

The two review findings, both blocking:

- A malformed cost (NaN, ±inf, negative) was taken as real. `_charge` now counts a cost as known only when it is
  finite and at least 0 (`_known`). Any other cost that a run reports is unknown and is charged the run's reserve,
  or `max-cost` when the run has none (a free run, or a start more than 7 days old). This holds for `agent.ran`,
  `agent.failed` and `budget.closed`. SPEC §9.9 says so. Test: `test_malformed_cost_counts_unknown`, run with NaN,
  -5, inf and -inf. In each case the fold charges the reserve, the permit refuses a run that would go over, and a
  free run's malformed cost is charged `max-cost`.
- `recover` read the record before it copied `OPEN`. It now copies `OPEN` first, under the flock, and then reads.
  A start cannot get in between, because starts take the flock. An end that comes after the copy is seen by the read.
  SPEC §9.9 says so. Test: `test_recover_copies_open_before_reading` wraps `read` so that the run writes its end and
  leaves `OPEN` just after the read returns. That is the gap in the old order. The test asserts that no
  `budget.closed` is written and that the run is charged its real 0.1.

I broke the code by hand to check that each new test fails. With `_known` reduced to "is a number", all four
`test_malformed_cost_counts_unknown` cases fail. With the copy moved back after the read,
`test_recover_copies_open_before_reading` fails. Both changes were then undone.

Tests run, one file or batch at a time: `tests/test_run_budget.py` (30 passed),
`test_upkeep_template.py` with `test_run_costs.py` and `test_rollup.py` (75 passed), `test_item_index.py` (55 passed),
`test_resilience.py` with `test_messages.py` (60 passed), and `test_runner_and_state.py` (43 passed). ruff is clean.
I did not run the whole unit suite or the four browser files here. The factory runs them under the watchdog after this
round. A shell loop that ran several test files in turn was refused (Bash, "don't ask" mode). I ran those files as
separate commands instead.

Round 3: main (e5d8c220) is merged in. The one conflict was in `Engine.start_all`. Main now writes
`ergostat.started` only from the lead shard. The branch's `budget.recover` runs after it and still runs on every
engine. That is the more reversible choice: recovery is idempotent under the flock, and it closes only runs whose
pid is gone, or runs of this pid that `OPEN` does not list. `OPEN` is shared by all the engines in a process.
No other code changed. Net lines outside `tests/`, `docs/` and `dev/`: 347 of the 380.

Tests run, one batch at a time: `tests/test_run_budget.py` (30 passed), `test_engine_shard_asks.py` with
`test_calls.py` (25 passed), and `test_daemons.py` with `test_leases.py` and `test_resilience.py` (111 passed).
ruff is clean. I did not run the whole unit suite or the four browser files here. The factory runs them.
