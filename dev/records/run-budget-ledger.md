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

## Where it stopped
Built in 87deb72b: items 1 to 4, and the docs of item 5 (SPEC §9.9 and the two measure tables, the agent guide §3b,
the GAPS entry under *Runtime*, the schema). The net count outside `tests/`, `docs/` and `dev/` is 170 lines,
including the 20 lines of schema JSON. The seven acceptance tests pass, and so does ruff. Each guard was broken by
hand and seen to fail its test: a denylist `free`, a malformed cost counted 0, the 24 h test on ends removed, starts
keyed by item, `left` returning `daily` when the record raises, and expired leases dropped from `reserved`.

Round 2 (the review's four findings):
- Free runs are now left out of the fold. `fold` takes the spec (`left` passes it) and names each run's block from
  its events (a lease's `block`, an `agent.*` event's item, a `budget.closed`'s `block`). A run is left out, reserve
  and ends alike, only when every block named is declared and `free`. With no spec, no block named, or a block not
  in the model, the run is charged. New test: `test_free_block_runs_fold_to_nothing`. A program block's run with no
  cost is charged nothing, while an ai block's and an unknown block's runs are charged `max-cost`.
- A `budget.closed` counts only when its source is `ergostat`. A forged one from a block's source, `record` or
  `intake` releases nothing (added to `test_reserve_held_until_end_with_cost`).
- Budget compile errors now carry the loader's location (`data.at("budget")`, kept as `Doc.budget_at`). They are
  checked in `test_check_budget_keys`.
- The merge, as this clone shows it: `refs/heads/main` is at 7c46bc6d, and this branch merged it in 8a542f6b
  (its second parent is 7c46bc6d, and `git log HEAD..main` lists nothing). The review names 7c46bc6d as origin/main. Here,
  `git log -1 origin/main` answers "unknown revision" (that is the command's output, not a claim about the factory's
  clone), so the merge used is of `main` at that same commit. The round-1 paragraph that called main c9d3bab5 was
  wrong and has been replaced.
- Each new guard was broken by hand and seen to fail its test: the source check dropped, `free` never applied (spec
  None), a block not found counted as free, and the location set to None.
- Run here: `tests/test_run_budget.py` (8 passed), test_spec_schema, test_spec_structure and test_local_settings
  (41 passed), test_run_costs and test_runner_and_state (57 passed). Ruff is clean. The unit suite and the four
  browser files were not run here: the brief leaves them to the factory and the merge queue.

Overrun reason: 190 net lines against 170. The 20 extra lines are the round-2 review fixes: applying the free-run allowlist in the fold (`_charged` and the block per run), the `budget.closed` source check, and the compile error location.

Choices the definition left open, each the more reversible one and each said in SPEC §9.9:
- A `ergostat.lease.taken` with no `reserve`, or a malformed one, reserves `max-cost`. No lease carries a reserve
  until `run-budget-permit`, so every unended leased run holds `max-cost` for now. This fails closed.
- An `agent.started` with no `reserve` is not a reserving event (as the definition says). So any unleased
  charged run before the permit counts only when it ends, and a malformed cost there is charged `max-cost`. (A free
  block's run counts nothing at all, as of round 2.)
- An end with no run id (no `causedby`, or a `budget.closed` with no `run`) is not matched and is not charged. A
  person's answer (`agent.ran` from `inbox/answer.py`) has none. The engine's ends always carry theirs.
- `budget:` written empty is two errors (both keys missing), not "no budget".
