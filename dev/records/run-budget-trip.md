# run-budget-trip: trip T1, a charged run's AI sessions capped at what is left of its reserve, and the run stopped when its reported cost reaches it
depends-on: [run-budget-reserve]

## Definition of done

Applies only when `budget:` is declared. Reserves and charged runs are as defined by `run-budget-reserve`.

1. **The run's cap is given to it.**
   - Every block run gets `ERGOSTAT_MAX_COST` set to its reserve (0 for a free run). It is removed from the environment when no budget is declared, so a run never inherits one.
   - An `ai` block with no `run:` whose command is Claude Code gets `--max-budget-usd <reserve>` added to its command line.
2. **Sessions take from the run's reserve under a lock.** `ergostat session` inside a run (`ERGOSTAT_RUN` and `ERGOSTAT_MAX_COST` set) keeps a ledger at `<state dir>/budget/<run>.jsonl`. It holds `fcntl.flock` on the ledger while it does three things: reads the entries, computes left = max-cost − Σ(each entry's cost, or its reserve while unfinished or of unknown cost), and appends its own entry reserving all of `left`. Then:
   - When `left` ≤ 0, or the ledger is unreadable, or `ERGOSTAT_MAX_COST` is not a number: it starts no `claude`, prints `session.failed` with the note `budget: …`, and exits 1.
   - Otherwise it starts `claude` with `--max-budget-usd <left>`, and at its end it writes its real cost (null if unknown) under the flock.
   - The run id must match `^[0-9a-f]{32}$`, and the path must resolve under `<state dir>/budget/`. Otherwise the session refuses.
   - The engine deletes only the run's own ledger file, by that validated name, when the run ends.
3. **T1, the trip.** In `run_block`, after each line that adds AI usage to the run, the engine checks the run's reported cost. When the known total is ≥ its reserve, or any reported part has an unknown cost in a run whose reserve is 0, it kills the run's process group (it was started with `start_new_session`) through the existing `killing` path. The run ends `agent.failed` with the note `stopped at its spend cap (T1)` and its full reported cost, which the fold from `run-budget-reserve` charges. T1 cannot be bypassed: no config key or flag turns it off.
4. **The claims, stated narrowly in SPEC.**
   - A session started with `ergostat session` is capped by Claude Code's `--max-budget-usd`. Claude Code enforces it between turns, so a session can pass its share by one turn's cost.
   - A program that runs `claude` itself, not through `ergostat session`, is seen only when its result line arrives. T1 stops it after that line, not before.
   - The day's budget is held by P3 (`run-budget-reserve`) charging actual costs. T1 bounds how far one run goes past its reserve.
5. The house rules are met: the acceptance tests pass; the unit suite and the four browser files pass with rc 0; ruff is clean; origin/main is merged in and the suites are run again. GAPS.md marks T1 as done.

## Files to touch

- `docs/roadmap/overnight/run-budget-trip.md` (the definition, first commit)
- `ergostat/costs/budget.py` (the ledger: path check, take, settle, remove)
- `ergostat/session.py` (take from the ledger before `claude`, the cap flag, settle at the end, refusal)
- `ergostat/spec/engine.py` (`ERGOSTAT_MAX_COST`, `--max-budget-usd` for `ai` blocks, the T1 check in `take`, ledger removal)
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`
- `tests/test_run_budget_trip.py` (new)

## Risks

- **lesson-1.** Two sessions of one run (in parallel, or one right after another) read `left` before either records its share. The ledger flock must span the read and the append of the reservation.
- **lesson-3.** An unreadable ledger, a session of unknown cost, a missing or garbled `ERGOSTAT_MAX_COST`, or a free run that reports AI usage with no price must each refuse or stop, never count as 0.
- **lesson-6.** T1 must kill the whole process group, not only the shell, and the run's end must say it was stopped.
- **lesson-8.** Claims about Claude Code's cap and about programs that run `claude` directly are narrowed as in point 4. No "never above" claim is made for T1.
- **lesson-9.** Each test below is broken against its guarded code, and that is reported.
- **lesson-10.** The trip test waits for the kill by polling with a bound, not a fixed sleep.
- **lesson-11.** The ledger path is built from `ERGOSTAT_RUN`. Validate it, resolve it under the state dir, and delete only that file.
- **lesson-12.** Every review finding is answered.
- **lesson-13.** Failures outside the gap are reported, not fixed.

## Acceptance tests

All in `tests/test_run_budget_trip.py`.

- `test_ai_block_given_max_budget`: a charged `ai` block's command has `--max-budget-usd` equal to its reserve. A block with `run:` does not, but its environment has `ERGOSTAT_MAX_COST`. Without `budget:`, neither, and an inherited `ERGOSTAT_MAX_COST` is removed.
- `test_session_capped_at_run_left`: `ERGOSTAT_CLAUDE` is a fake that records its args. The second session of a run is given `--max-budget-usd` = reserve − the first session's cost.
- `test_session_unknown_cost_counts_reserve`: a ledger entry with null cost leaves nothing, and the next session refuses. (lesson-3)
- `test_session_refused_when_nothing_left`: with `ERGOSTAT_MAX_COST=0`, the fake `claude` is never started (no marker file), `session.failed` says budget, and rc is 1.
- `test_session_refuses_unreadable_ledger`: a garbled ledger or a non-numeric `ERGOSTAT_MAX_COST` gives a refusal with no `claude` started. (lesson-3)
- `test_session_ledger_lock_spans_append`: `budget._ledger_between` is monkeypatched to start a second session's take in a thread and wait up to 1 s for its read. The test asserts that only one gets a positive share. With the flock removed it fails. (lesson-1)
- `test_ledger_path_validated`: `ERGOSTAT_RUN=../x` or a non-hex id gives a refusal and no file outside `<state dir>/budget/`. At the run's end only that run's file is removed, and a neighbouring file survives. (lesson-11)
- `test_run_stopped_at_cap`: a program block prints a `session.ran` line costing ≥ its reserve, then starts a `sleep 60` child. The run ends `agent.failed` with `stopped at its spend cap (T1)` within a polled bound, and the child pid is gone. With the T1 check removed it fails. (lesson-6)
- `test_free_run_stopped_on_ai_use`: a free run that reports a session with unknown cost is stopped. (lesson-3)
- `test_trip_cost_charged`: the stopped run's full reported cost (above its reserve) is what `ergostat.budget.left` subtracts.

## Size budget

200 net lines of code outside `tests/` and `docs/`.

## Notes from the plan review (answer each)

- T1's rule (point 3) trips on the known total >= reserve and treats an unknown-cost part as a stop only when the reserve is 0. In a charged run, a program running claude directly that reports usage with no price adds 0 and is never stopped (lesson-3, failing open). The rule must count any unknown-cost part as the whole reserve, so it trips whatever the reserve. Add an acceptance test where a charged run (reserve > 0) reports a session of unknown cost and is stopped, and show it fails against the current rule.
- Parsing ERGOSTAT_MAX_COST must reject nan, inf and negative values (float('nan') passes 'is a number' and nan <= 0 is false). Add them to test_session_refuses_unreadable_ledger.
- If only one of ERGOSTAT_RUN and ERGOSTAT_MAX_COST is set, the session must refuse, not run with no cap. Test it.
- State in SPEC that a session reserves all of what is left, so a second session running at the same time in one run always refuses.
- An ai block's own claude is capped at the full reserve but not written to the ledger, so ergostat sessions started inside it also see the full reserve. Either write the block's spend to the ledger or state the up-to-2x overshoot before T1 in SPEC.
- If the user's ai command already has --max-budget-usd, the engine's value must win. Test it.
- A session that settles after the engine has deleted the run's ledger must not create the file again.

## Where it stopped

Nothing of T1 is built. The gap depends on `run-budget-reserve` (`depends-on: [run-budget-reserve]`), and that gap is
not in this clone. It has no `ergostat/costs/budget.py`, no `budget:` key in the spec loader (`PER_MACHINE` and the
top-level keys) or the schema, no reserve, no charged/free allowlist, no `permit` and no fold that charges a run's
reported cost. `git for-each-ref` shows only `refs/heads/main` and `refs/heads/factory/run-budget-trip`, so there is
no branch to merge it from either. The parent gap `run-budget-permissive` is parked, and both of its sub-gaps were
deferred by the coordinator.

Every point of the definition (the run's reserve as `ERGOSTAT_MAX_COST`, the ledger capped at the reserve, T1
comparing the reported cost with the reserve, and `test_trip_cost_charged` reading `ergostat.budget.left`) needs
the reserve as `run-budget-reserve` defines it. If T1 built its own `budget:` config and reserve, it would be building
that other gap inside this one, which the house rules forbid. I took the more reversible option and changed no code.

Left: everything in "Definition of done", points 1 to 5, and all ten acceptance tests. Land `run-budget-reserve` on
main first, then run this gap again from that main. The plan-review notes above still need answers when it is
built: an unknown cost counted as the whole reserve in charged runs, nan/inf/negative caps rejected, a refusal when
only one of `ERGOSTAT_RUN` or `ERGOSTAT_MAX_COST` is set, the SPEC sentence on a second concurrent session, the
up-to-2x overshoot of an `ai` block's own claude, the engine's `--max-budget-usd` winning, and no ledger re-created
after its removal.
