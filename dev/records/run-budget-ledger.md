# run-budget-ledger: `budget: {daily, max-cost}` compiled and bounded, the day's spend folded by run id (fail closed), and `ergostat.budget.left`
depends-on: []

## Definition of done
The parked `factory/run-budget-reserve` built all of P3 (`ergostat/costs/budget.py`, 204 lines). This branch lifts only the config, the fold and the measure. Nothing is refused yet. When done:
1. **Config.** `ergostat.yaml` takes a top-level `budget:` with `daily` and `max-cost`, both required. `daily` is US dollars over the trailing 24 h, with 0 < daily ≤ 10000. `max-cost` is what a run reserves, with 0 < max-cost ≤ daily. Each of these is its own compile error: an unknown key, a missing key, a non-number, a value out of bounds. `ergostat.local.yaml` may not set it. Without `budget:`, nothing changes. The schema and SPEC (new §9.9) describe it. SPEC calls `max-cost` only what a run reserves before it starts, never a cap on what the run spends.
2. **Which runs are charged.** This is an allowlist. A run is *free* only when its block's type is not `ai` and its agent is declared with kind `person`, `decision`, `program` or `rule`. Every other run is *charged*, including one with no agent or no kind.
3. **The fold** (`ergostat/costs/budget.py`). It is keyed by run id, never by lease state or time order. It reads reserving events (`ergostat.lease.taken`, `agent.started` with a `reserve`) and ends (`agent.ran`, `agent.failed`, `budget.closed`) over 7 days. An end is matched to its start by run id. An end's charge counts only while the end is within the last 24 h. A run's charge:
   - with no end: its reserve;
   - with a known cost (finite and ≥ 0): that cost;
   - with a missing or malformed cost (NaN, ±inf, negative): its reserve, or `max-cost` when it has no reserving event;
   - with several ends: the largest charge.

   A lease that expired or was released without an end still holds its reserve. A run started 3 days ago and ended 2 days ago is charged 0.
4. **Measure.** `ergostat.budget.left` = daily − spent − reserved. It raises `MeasureError` when no `budget:` is declared or the record can't be read. It never returns `daily` or 0 in those cases.
5. SPEC §9.9, the agent guide and GAPS say what is in and what is left for `run-budget-permit`. House rules: the unit suite and four browser files pass, ruff is clean, and origin/main is merged in and the suites run again. "Where it stopped" says only what this clone shows: `origin/main` is present here, so no sentence may claim it is missing.

## Relation to other work
- run-budget-permit: builds on this branch; it adds the permit and recovery.
- run-budget-trip (ready): touches `ergostat/costs/budget.py` after this branch; it waits for the P3 sub-gaps.
- ergostat-s-own-ai-calls-under-the-budget (leased): later; it reads this fold.

## Files to touch
- `dev/records/run-budget-ledger.md` (new)
- `ergostat/costs/budget.py` (new)
- `ergostat/spec/ir.py`
- `ergostat/spec/load.py`
- `ergostat/spec/compile.py`
- `ergostat/numbers/measures.py`
- `schema/ergostat.schema.json`
- `docs/SPEC.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`
- `tests/test_run_budget.py` (new)

## Risks
- lesson-3: an expired lease, a missing or malformed cost, or an unreadable record counted as 0, or `left` reported anyway.
- lesson-4: `daily` and `max-cost` move money; each needs a ceiling.
- lesson-5: a retaken item's new run must not clear or merge the old run's reserve.

## Acceptance tests
- `tests/test_run_budget.py::test_check_budget_keys`: one compile error for each bad key or value, a valid budget compiles, and the local file is refused.
- `tests/test_run_budget.py::test_free_run_allowlist`: a `program` agent on a non-`ai` block is free; a block with no agent, or an `ai` block, is charged. Fails as a denylist.
- `tests/test_run_budget.py::test_reserve_held_until_end_with_cost`: a lease taken then expired with no end is charged its reserve; after `agent.ran` with cost 0.1 it is charged 0.1.
- `tests/test_run_budget.py::test_malformed_cost_counts_unknown`: missing, NaN, −5, inf and −inf costs are charged the reserve, or `max-cost` for a free run.
- `tests/test_run_budget.py::test_window_by_run_id`: started 3 d ago and ended 2 d ago is charged 0; started 2 d ago with no end is charged its reserve; started 8 d ago, ended 1 h ago and priced is charged its cost.
- `tests/test_run_budget.py::test_retaken_item_keeps_old_reserve`: two run ids, each charged once.
- `tests/test_run_budget.py::test_budget_left_fails_closed`: the value over a mix of runs; `MeasureError` with no budget and with `events.query` raising; `all_of` gives None plus `_error`.

## Size budget
170 net lines
size: L (confidence: medium)
